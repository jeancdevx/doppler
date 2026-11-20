export const DOPPLER_DEFAULTS = {
  maxFileBytes: 26_214_400,
  maxDurationSeconds: 120,
  minWindowSeconds: 3.0,
  windowSeconds: 3.0,
  hopSeconds: 1.5,
  retentionHours: 24,
  threshold: 0.6547843813896179,
  sampleRate: 16_000,
  nMels: 64,
  nFft: 2048,
  stftHop: 512
} as const

export const WORKFLOW_STEPS = [
  {
    index: '01 / CARGA DIRECTA',
    title: 'Valida y sube a almacenamiento privado.',
    description:
      'El navegador comprueba la cabecera WAV antes de enviar. La API Rust emite una firma PUT temporal hacia Cloudflare R2 sin exponer credenciales ni abrir el bucket.'
  },
  {
    index: '02 / PREPARACIÓN FIEL',
    title: 'Reproduce el contrato exacto del experimento.',
    description:
      'Cada archivo pasa a mono 16 000 Hz con soxr_hq, normalización de pico a 0,99 y ventanas completas de 3,0 s con salto de 1,5 s sobre matrices Log-Mel de 64 × 94.'
  },
  {
    index: '03 / REVISIÓN Y EXPORTACIÓN',
    title: 'Inspecciona cada ventana en su contexto.',
    description:
      'Escucha el audio original mediante acceso temporal autorizado, compara el score sigmoide frente al umbral congelado y exporta resultados trazables en JSON o CSV.'
  }
] as const

export const ARCHITECTURE_BENTO = [
  {
    eyebrow: 'MODELO CONGELADO',
    title: 'ResNet18 sobre Log-Mel nativo 64 × 94',
    detail:
      'Carga estricta en CPU desde checkpoint verificado por SHA-256. Sin descargas ImageNet en arranque, sin redimensionado a 224 × 224 y sin recalibración del umbral 0,6548.',
    metric: '122 tensores · float32 CPU'
  },
  {
    eyebrow: 'ALMACENAMIENTO R2',
    title: 'Bucket privado con URLs firmadas de corta duración',
    detail:
      'Las credenciales residen exclusivamente en la API Rust. Cada objeto usa clave aleatoria por sesión, verificación real de tamaño mediante HeadObject y purga automática a las 24 h.',
    metric: 'PUT 5 min · GET 3 min · TTL 24 h'
  },
  {
    eyebrow: 'COLA PERSISTENTE',
    title: 'Despachador acotado en SQLite con recuperación',
    detail:
      'Una inferencia concurrente para proteger memoria y CPU locales. Las transiciones de estado quedan auditadas en SQLite y los trabajos interrumpidos se recuperan tras reiniciar.',
    metric: 'Concurrencia 1 · Cola acotada'
  }
] as const

export const FAQ_ITEMS = [
  {
    id: 'overlapping-windows',
    tag: 'SOLAPAMIENTO',
    question:
      '¿Por qué el número de ventanas positivas no equivale a segundos exactos de sirena?',
    answer:
      'El modelo evalúa ventanas completas de 3,0 segundos desplazadas cada 1,5 segundos. Como las ventanas se solapan un 50 %, un evento breve puede activar dos o más ventanas consecutivas. Además, la etiqueta indica presencia en la ventana completa, no la marca exacta de inicio ni fin de la sirena.'
  },
  {
    id: 'short-files',
    tag: 'CLIP CORTO',
    question: '¿Qué ocurre si cargo un archivo WAV de menos de 3 segundos?',
    answer:
      'Conforme al contrato de preparación del experimento (drop_short_clip), los audios menores de 3,0 s tras remuestrear a 16 000 Hz no se rellenan con silencio ni se clasifican artificialmente. El estudio explica el motivo y muestra las características decodificadas del archivo.'
  },
  {
    id: 'score-meaning',
    tag: 'SCORE SIGMOIDE',
    question: '¿El score del modelo es un porcentaje de confianza?',
    answer:
      'No. El score corresponde a la salida sigmoide sin calibrar del clasificador binario (sigmoid_probability_not_calibrated). Sirve para decidir frente al umbral congelado 0,6548 obtenido en validación cruzada, pero no debe interpretarse como probabilidad calibrada ni certeza absoluta.'
  },
  {
    id: 'global-classification',
    tag: 'ALCANCE',
    question: '¿Por qué no existe una clasificación global única del archivo?',
    answer:
      'El detector fue entrenado y evaluado a nivel de ventana de 3,0 s. Agregar una decisión global del archivo sin una regla validada experimentalmente introduciría afirmaciones no respaldadas. En su lugar, Doppler presenta cada ventana individual, el resumen de positivas y la unión visual de intervalos.'
  },
  {
    id: 'retention-privacy',
    tag: 'PRIVACIDAD R2',
    question: '¿Dónde se guarda mi audio y durante cuánto tiempo?',
    answer:
      'El archivo WAV se almacena en un bucket privado de Cloudflare R2 bajo un prefijo exclusivo de Doppler. Solo tu sesión firmada puede solicitar una URL temporal de reproducción o descargar resultados. Puedes eliminar el archivo y sus resultados inmediatamente desde el estudio; además, una tarea automática purga objetos y registros a las 24 horas.'
  },
  {
    id: 'formats-limits',
    tag: 'LÍMITES WAV',
    question: '¿Qué archivos y límites técnicos admite esta versión?',
    answer:
      'Admite únicamente archivos WAV (mono o multicanal, remuestreados internamente a 16 000 Hz con soxr_hq) de hasta 25 MiB y 120 segundos. La cola residual incompleta al final del audio (si no completa otra ventana de 3,0 s) se descarta y se informa en la trazabilidad.'
  }
] as const
