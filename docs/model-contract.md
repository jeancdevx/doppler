# Contrato del Modelo e Inferencia — Doppler (`05_resnet18`)

Este documento congela la especificación técnica exacta del modelo entrenado **ResNet18 sobre representaciones Log-Mel** y su pipeline de preparación acústica. Cualquier desviación en decodificación, remuestreo, normalización, segmentación, espectrograma, estandarización, arquitectura o umbral invalida la fidelidad respecto al experimento académico original.

## 1. Fuentes verificadas y trazabilidad

| Artefacto | Origen | Hash SHA-256 / Revisión |
| --- | --- | --- |
| Repositorio ML de referencia | `https://github.com/jeancdevx/doppler-ml` (rama `develop`) | Commit `baacec8d9427bf42c001ab5ca9c13343e2ec0c60` |
| Checkpoint entrenado (`model.pt`) | `Doppler_Espectro_Brand_Kit/model/model.pt` (idéntico al registrado en `doppler-ml/docs/modelos/evidencia/05_resnet18/reports/artifact_hashes.json`) | `e0dc2eaa1415f66d7442a8db7cf249129520ece20d575df35dc0aefb29f89d2a` |
| Configuración de inferencia (`inference.json`) | `Doppler_Espectro_Brand_Kit/model/inference.json` (idéntico al hash registrado en `doppler-ml`) | `02b2a9884628a391cedfbf36803a775f85357fed05fb2549e3c01da157736557` |
| Notebook de preparación | `Doppler_Espectro_Brand_Kit/notebooks/00_preparacion_insumos.ipynb` | `50c00b1cac00781e8004f64f467de23e02d9fe2807d5897f5ce5a9fd0e99c575` |
| Notebook de entrenamiento | `Doppler_Espectro_Brand_Kit/notebooks/05_resnet18.ipynb` | `2471807ace54ceb58c7302801f5c56ecf30deb48c48d6730f5ebcd4f021d02c0` |
| Documentación histórica del modelo | `doppler-ml/docs/modelos/05_resnet18.md` | Revisión `baacec8d9427bf42c001ab5ca9c13343e2ec0c60` |

> **Nota sobre el estado histórico de los documentos:** `doppler-ml/docs/modelos/05_resnet18.md` refleja la ejecución del 12 de octubre de 2026 donde la evaluación externa sobre `LSSiren` figuraba pendiente (`external_evaluated=false`). El contexto actual del proyecto confirma que los apartados académicos de evaluación e interpretabilidad ya concluyeron y que esta entrega corresponde a la implementación funcional y validación local (etapa previa a la redacción de la sección 9).

### Entorno histórico del entrenamiento (Kaggle)

Según `docs/modelos/evidencia/05_resnet18/reports/environment.json` y `torch_environment.json`:

- Python `3.13.15` (`Linux-6.18.48+-x86_64-with-glibc2.39`)
- `torch==2.11.0+cu128`, `torchvision==0.26.0+cu128`
- `numpy==2.1.3`, `scipy==1.16.3`, `scikit-learn==1.6.1`, `pandas==2.3.3`
- Hardware de entrenamiento: 2 × NVIDIA Tesla T4 (GPU). **Las latencias GPU de Kaggle no representan el rendimiento CPU local ni el de un servidor de producción.**

## 2. Verificación del checkpoint (`model.pt`)

Inspección directa de `Doppler_Espectro_Brand_Kit/model/model.pt` (43 MiB, archivo ZIP de serialización PyTorch):

- **No es un `.pth` de pesos ImageNet crudos.** Contiene el diccionario exportado por `05_resnet18.ipynb` (celda 86):
  - `state_dict`: `OrderedDict` con **122 claves**, desde `net.conv1.weight` (`(64, 3, 7, 7)`) hasta `net.fc.1.weight` (`(1, 512)`) y `net.fc.1.bias` (`(1,)`).
  - `model_kind`: `"resnet"`
  - `params`: `{"lr": 0.001, "weight_decay": 0.0001, "dropout": 0.3, "final_epochs": 4}`
  - `threshold`: `0.6547843813896179`
  - `score_type`: `"sigmoid_probability_not_calibrated"`
  - `input_shape`: `[64, 94]`
  - `class_map`: `{"0": "NON_EMERGENCY", "1": "EMERGENCY"}`
  - `normalization_mean`: vector de 64 flotantes (coincide valor a valor con `inference.json`)
  - `normalization_std`: vector de 64 flotantes (coincide valor a valor con `inference.json`)
  - `config`: diccionario `CFG` completo de la ejecución de entrenamiento.

## 3. Arquitectura exacta (`VisualTransfer`)

Extraída literalmente de `05_resnet18.ipynb` (celdas 71, 72 y 84):

```python
class VisualTransfer(nn.Module):
    def __init__(self, dropout: float, initialize_pretrained: bool = False):
        super().__init__()
        self.net = resnet18(weights=None)
        self.net.fc = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(self.net.fc.in_features, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x.repeat(1, 3, 1, 1)).squeeze(1)
```

Reglas obligatorias en inferencia:

1. Instanciar `resnet18(weights=None)` — **nunca** descargar pesos ImageNet al arrancar.
2. Reemplazar `self.net.fc` por `nn.Sequential(nn.Dropout(params["dropout"]), nn.Linear(512, 1))`, preservando los índices de clave `net.fc.1.weight` y `net.fc.1.bias`.
3. Cargar `artifact["state_dict"]` con `strict=True` y `torch.load(path, map_location="cpu", weights_only=True)`.
4. Activar `model.eval()` de forma permanente (fija BatchNorm con sus `running_mean`/`running_var` y desactiva Dropout).
5. Ejecutar en CPU dentro de `torch.inference_mode()` **sin AMP** (`float32` estricto).
6. **Prohibido** redimensionar a `224×224`, aplicar normalización ImageNet (`[0.485, 0.456, 0.406]`), mapas de color RGB o recortes espaciales. La entrada se mantiene en resolución nativa `(B, 1, 64, 94)` y se repite a 3 canales mediante `x.repeat(1, 3, 1, 1)`.

## 4. Pipeline de preparación acústica

Extraído literalmente de `00_preparacion_insumos.ipynb` (celdas 2, 37, 46, 47, 48, 49 y 50):

| Etapa | Parámetro / Regla efectiva |
| --- | --- |
| Formato admitido | WAV únicamente (verificación por cabecera RIFF/WAVE y decodificador) |
| Decodificación | `soundfile.read(path, dtype="float32", always_2d=True)` con fallback `scipy.io.wavfile.read` normalizado a `float32` en `[-1, 1]`. Rechazar `sr <= 0`, vacío, `< 1` canal o valores no finitos (`NaN`/`Inf`). |
| Reducción de canales | Promedio aritmético entre canales del WAV: `mono = a.mean(axis=1).astype(np.float32)` |
| Frecuencia de muestreo objetivo | `SR = 16000` Hz |
| Remuestreo | Si `sr != 16000`: `librosa.resample(mono, orig_sr=sr, target_sr=16000, res_type="soxr_hq")` |
| Normalización de amplitud | Pico por archivo completo (`peak_per_file`): `peak = float(np.max(np.abs(mono)))`. Si `peak > 0`: `mono = mono * (0.99 / peak)`. Si `peak == 0` (silencio puro), se conserva sin dividir por cero y **no se sustituye el clasificador por una regla de silencio**. |
| Ventana y salto | `window_seconds = 3.0` (`N = 48000` muestras), `hop_seconds = 1.5` (`H = 24000` muestras). |
| Política de archivos cortos | `drop_short_clip`: si `len(mono) < 48000` (< 3,0 s tras remuestrear), se generan **0 ventanas completas** y **no se rellena silenciosamente**. El servicio informa el motivo coherente con el contrato. |
| Política de cola incompleta | `drop_incomplete_tail`: `starts = range(0, max(0, len(mono) - 48000 + 1), 24000)`. Las muestras residuales después de `last_start + 48000` se descartan y se reportan como `discarded_tail_seconds` / `discarded_tail_samples`. |
| STFT | `n_fft = 2048`, `hop_length = 512`, `win_length = 2048`, `window = "hann"` (periódica por defecto en `librosa.stft`), `center = True`, `pad_mode = "constant"`. |
| Espectro de potencia | `power = np.abs(librosa.stft(x, ...)) ** 2` (`power = 2`). |
| Banco de filtros Mel | `librosa.filters.mel(sr=16000, n_fft=2048, n_mels=64, fmin=20.0, fmax=8000.0, htk=False, norm="slaney")` (escala Slaney, normalización de área Slaney). |
| Proyección Mel | `mel = MEL_BASIS @ power` |
| Conversión a dB | `librosa.power_to_db(mel, ref=np.max, amin=1e-10, top_db=80.0).astype(np.float32)` (referencia máxima por segmento, rango dinámico 80 dB). |
| Forma y dtype de matriz | `(64, 94)` (`[n_mels, 1 + 48000 // 512]`), `float32`, todos los valores finitos. |

## 5. Normalización de tensor, scores y decisión

1. **Estandarización por banda (estadísticas congeladas del conjunto de entrenamiento):**
   - `mean` (`float32`, shape `(64,)`) y `std` (`float32`, shape `(64,)`) leídos directamente desde `model.pt` y validados contra `inference.json`.
   - `tensor = (logmel - mean[:, None]) / std[:, None]`
   - Nunca recalcular media ni desviación estándar sobre el audio del usuario.
2. **Orientación del lote:** `(batch_size, 1, 64, 94)` en `torch.float32`.
3. **Score:** `score = torch.sigmoid(logits.float()).cpu().numpy()` en `[0, 1]`.
   - Tipo documentado: `sigmoid_probability_not_calibrated`.
   - **No** debe presentarse como porcentaje de confianza ni probabilidad calibrada.
4. **Umbral y mapeo de clases:**
   - Umbral congelado: `0.6547843813896179`.
   - `score >= threshold` → `"EMERGENCY"` (clase positiva, `1`).
   - `score < threshold` → `"NON_EMERGENCY"` (clase negativa, `0`).
5. **Interpretación temporal:**
   - Las ventanas tienen una duración de 3,0 s y se solapan 1,5 s entre consecutivas.
   - Una ventana `EMERGENCY` indica detección en ese intervalo completo; no localiza el instante exacto de inicio o fin de la sirena.
   - El número de ventanas positivas es distinto del tiempo total de audio cubierto.
   - No existe una clasificación global de archivo validada experimentalmente; el sistema muestra el resumen por ventanas y, si agrega intervalos visuales unidos, indica explícitamente que son uniones derivadas de ventanas solapadas de 3,0 s.

## 6. Identificador del contrato

`CONTRACT_VERSION = "doppler-resnet18-v3-contract-1.0.0"`

Cada ejecución de inferencia devuelve y persiste:
- `contract_version` y `contract_sha256` (hash SHA-256 de la especificación efectiva de parámetros + `normalization_mean` + `normalization_std` + `threshold`),
- `model_sha256` (`e0dc2eaa1415f66d7442a8db7cf249129520ece20d575df35dc0aefb29f89d2a`),
- `audio_sha256` (hash SHA-256 del WAV analizado),
- `threshold` efectivo (`0.6547843813896179`).
