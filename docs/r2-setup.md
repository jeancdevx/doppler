# Configuración y Comprobación de Cloudflare R2 — Doppler

## 1. Requisitos del bucket y credenciales

- Crea un **bucket privado** de desarrollo en Cloudflare R2 (por ejemplo, `doppler-dev-audio` o `doppler-bucket`). **No habilites Public Development URL ni acceso público.**
- Genera un token S3 API de Cloudflare R2 con alcance limitado al bucket elegido:
  - Para ejecución de la aplicación: **Object Read & Write** (mínimo privilegio).
  - Para configurar CORS automáticamente por API (`PutBucketCors`): **Admin Read & Write** o configurar la política desde el panel web de Cloudflare.
- Copia `.env.example` a `.env` y completa `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_PREFIX` y `R2_TEST_PREFIX`.
- **Nunca** incluyas `.env` en Git, Docker, frontend, logs ni evidencias.

## 2. Política CORS exacta para el origen local

Para que el navegador realice subidas `PUT` directas con progreso real y descargas temporales `GET` desde `http://localhost:4321`, el bucket debe tener la política CORS definida en [config/r2-cors.json](../config/r2-cors.json):

```json
[
  {
    "AllowedOrigins": [
      "http://localhost:4321"
    ],
    "AllowedMethods": [
      "PUT",
      "GET",
      "HEAD"
    ],
    "AllowedHeaders": [
      "content-type"
    ],
    "ExposeHeaders": [
      "etag"
    ],
    "MaxAgeSeconds": 3000
  }
]
```

> **Importante sobre R2:** Cloudflare R2 requiere listar explícitamente las cabeceras permitidas (`content-type`) en lugar de depender de comodines `*`, y la petición `PUT` del navegador debe enviar exactamente los encabezados firmados en la URL (`Content-Type: audio/wav`). Asimismo, `aws-sdk-s3` en Rust desactiva el cálculo automático de checksum CRC32 (`RequestChecksumCalculation::WhenRequired`) para mantener compatibilidad con subidas XHR desde el navegador.

### Aplicar CORS desde el panel de Cloudflare (si el token es solo Object Read & Write)

1. Abrir **Cloudflare Dashboard → R2 Object Storage → `<tu-bucket>` → Settings → CORS Policy**.
2. Pegar el bloque JSON de `config/r2-cors.json` **conservando cualquier regla previa ajena al proyecto**.
3. Guardar los cambios.

## 3. Verificación reproducible

Ejecuta el comprobador incluido (lee `.env` sin imprimir secretos ni URLs firmadas completas):

```bash
python3 scripts/r2_check.py --ensure-cors
```

Comprueba automáticamente:
1. `HeadBucket` (acceso al bucket privado).
2. `GetBucketCors` / `PutBucketCors` (conservando reglas ajenas si el token tiene permiso).
3. `Presigned PUT` + `HeadObject` + `Presigned GET` + igualdad SHA-256 bajo `R2_TEST_PREFIX`.
4. Vencimiento real de URL `GET` prefirmada (TTL 2 s → rechazo HTTP 403 tras esperar 3,5 s).
5. `DeleteObject` + verificación HTTP 404 para no dejar residuos en el bucket.

## 4. Retención y seguridad de prefijos

- La API Rust únicamente opera sobre claves que comienzan por `R2_PREFIX` (`doppler/uploads/`).
- La limpieza automática cada `CLEANUP_INTERVAL_SECONDS` elimina únicamente objetos y trabajos creados por Doppler cuyo vencimiento (`RETENTION_HOURS`, por defecto 24 h) o abandono de subida haya expirado. **Nunca borra contenido ajeno del bucket.**
