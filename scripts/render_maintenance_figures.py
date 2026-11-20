#!/usr/bin/env python3
"""Genera figuras académicas (Figuras 34, 35, 36 + gráficas) en SVG y PNG y Tablas 44, 45, 46 (CSV + MD)
para el Capítulo 10 (Monitoreo y Mantenimiento) con la identidad visual Doppler / Espectro.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
import sys
from pathlib import Path


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def svg_figura_34_monitoreo_drift() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1160 660" width="1160" height="660" font-family="IBM Plex Sans, sans-serif">
  <defs>
    <marker id="arrBlue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#3156D3"/>
    </marker>
    <marker id="arrDark" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#172B4D"/>
    </marker>
    <marker id="arrAmber" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#B57B14"/>
    </marker>
  </defs>
  <rect width="1160" height="660" fill="#F5F3EC"/>
  <text x="40" y="42" font-size="22" font-weight="600" fill="#172B4D">Figura 34. Arquitectura de monitoreo operativo, telemetría desacoplada y detección de drift</text>
  <text x="40" y="65" font-size="13" fill="#52617B">Doppler · Validación local Linux Manjaro + Cloudflare R2 privado · Sección 10.1</text>

  <!-- Capa 1: Sondas y ejecución -->
  <rect x="40" y="96" width="320" height="235" rx="14" fill="#090F1D" stroke="#34435C" stroke-width="1.5"/>
  <text x="60" y="124" font-size="11" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">1. SONDAS Y OBSERVABILIDAD EN VIVO</text>
  <text x="60" y="150" font-size="16" font-weight="600" fill="#F5F3EC">Worker de salud (cada 60 s)</text>
  <text x="60" y="176" font-size="12" fill="#BDC4D1">• SQLite: SELECT 1 + tamaño (db/wal/shm)</text>
  <text x="60" y="198" font-size="12" fill="#BDC4D1">• Inferencia: GET /ready + hash checkpoint</text>
  <text x="60" y="220" font-size="12" fill="#BDC4D1">• Cloudflare R2: HeadBucket + uso prefijo</text>
  <text x="60" y="242" font-size="12" fill="#BDC4D1">• Endpoints: /api/health (200) y /api/ready (200/503)</text>
  <rect x="60" y="262" width="280" height="50" rx="8" fill="#101B30" stroke="#F0C779" stroke-width="1"/>
  <text x="72" y="283" font-size="11" font-weight="600" fill="#FFDF9F">Incidentes automáticos (N = 3 fallos)</text>
  <text x="72" y="301" font-size="11" fill="#BDC4D1">Apertura + cierre automático al recuperar</text>

  <!-- Capa 2: Pipeline observacional -->
  <rect x="40" y="365" width="320" height="230" rx="14" fill="#FFFFFF" stroke="#3156D3" stroke-width="2"/>
  <text x="58" y="393" font-size="10" font-family="IBM Plex Mono, monospace" fill="#3156D3">2. EXTRACCIÓN OBSERVACIONAL (PASIVA)</text>
  <text x="58" y="419" font-size="16" font-weight="600" fill="#172B4D">FastAPI + ResNet18 CPU</text>
  <text x="58" y="444" font-size="12" fill="#52617B">• Entrada: SR original, canales, duración, RMS,</text>
  <text x="58" y="463" font-size="12" fill="#52617B">  silencio, clipping, media/DE Log-Mel, centroide</text>
  <text x="58" y="487" font-size="12" fill="#52617B">• Salida: media/máx score sigmoide, tasa positiva</text>
  <text x="58" y="511" font-size="12" fill="#52617B">• Latencias: cola, R2, prep, inferencia, commit</text>
  <text x="58" y="542" font-size="10" font-family="IBM Plex Mono, monospace" fill="#145334">Paridad verificada: diff máx ≤ 1e-5 vs notebooks</text>
  <text x="58" y="562" font-size="10" font-family="IBM Plex Mono, monospace" fill="#145334">Umbral congelado: 0.6547843813896179</text>

  <!-- Capa 3: Persistencia desacoplada -->
  <rect x="420" y="96" width="340" height="499" rx="14" fill="#EAE8E1" stroke="#34435C" stroke-dasharray="6 4" stroke-width="1.5"/>
  <text x="440" y="124" font-size="11" font-family="IBM Plex Mono, monospace" fill="#172B4D">3. PERSISTENCIA DESACOPLADA EN SQLITE (WAL)</text>

  <rect x="440" y="144" width="300" height="102" rx="10" fill="#FFFFFF" stroke="#172B4D" stroke-width="1.5"/>
  <text x="456" y="168" font-size="13" font-weight="600" fill="#172B4D">jobs + job_windows (retención 24 h)</text>
  <text x="456" y="188" font-size="11.5" fill="#52617B">Se purgan junto con el WAV en R2 tras 24 h</text>
  <text x="456" y="206" font-size="11.5" fill="#52617B">o al borrar el usuario desde el Estudio.</text>
  <text x="456" y="226" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#B57B14">Auditoría en retention_runs</text>

  <rect x="440" y="266" width="300" height="145" rx="10" fill="#101B30" stroke="#9BB1FF" stroke-width="2"/>
  <text x="456" y="290" font-size="13" font-weight="600" fill="#F5F3EC">Historial operativo y drift (30 días)</text>
  <text x="456" y="312" font-size="11.5" fill="#BDC4D1">• health_samples · operational_incidents</text>
  <text x="456" y="332" font-size="11.5" fill="#BDC4D1">• job_telemetry_history (1 fila/archivo, UNIQUE)</text>
  <text x="456" y="352" font-size="11.5" fill="#BDC4D1">• Sin WAV ni nombres personales sensibles</text>
  <text x="456" y="372" font-size="11.5" fill="#86D6B8">Sobrevive al borrado de 24 h sin duplicar</text>
  <text x="456" y="392" font-size="10" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">Latencias p50/p95 por etapa y duración</text>

  <rect x="440" y="431" width="300" height="144" rx="10" fill="#FFFFFF" stroke="#3156D3" stroke-width="1.5"/>
  <text x="456" y="455" font-size="13" font-weight="600" fill="#172B4D">drift_references + drift_evaluations</text>
  <text x="456" y="476" font-size="11.5" fill="#52617B">• Referencia congelada (conservada tras purga)</text>
  <text x="456" y="496" font-size="11.5" fill="#52617B">• Verificación de hash modelo + extractor obs_v1</text>
  <text x="456" y="516" font-size="11.5" fill="#52617B">• Unidad de análisis: archivo (evita correlación</text>
  <text x="456" y="534" font-size="11.5" fill="#52617B">  entre ventanas solapadas de 3,0 s / salto 1,5 s)</text>
  <text x="456" y="556" font-size="9.5" font-family="IBM Plex Mono, monospace" fill="#3156D3">Wasserstein 1D norm. + cambio de proporciones</text>

  <!-- Capa 4: Motor de drift y consola -->
  <rect x="820" y="96" width="300" height="235" rx="14" fill="#FFFFFF" stroke="#B57B14" stroke-width="2"/>
  <text x="840" y="124" font-size="11" font-family="IBM Plex Mono, monospace" fill="#B57B14">4. EVALUACIÓN DE DRIFT SEPARADA</text>
  <text x="840" y="150" font-size="16" font-weight="600" fill="#172B4D">Estados explícitos</text>
  <text x="840" y="178" font-size="12" fill="#145334">• no_alert: distribución comparable</text>
  <text x="840" y="200" font-size="12" fill="#8F1D24">• drift_detected: entrada y/o salida</text>
  <text x="840" y="222" font-size="12" fill="#52617B">• insufficient_data: n &lt; mínimo</text>
  <text x="840" y="244" font-size="12" fill="#52617B">• no_reference: sin referencia cargada</text>
  <text x="840" y="266" font-size="12" fill="#8F1D24">• evaluation_error: hash/extractor ≠</text>
  <text x="840" y="302" font-size="11" font-family="IBM Plex Mono, monospace" fill="#B57B14">Marca si falta corpus real representativo</text>

  <rect x="820" y="365" width="300" height="230" rx="14" fill="#090F1D" stroke="#9BB1FF" stroke-width="2"/>
  <text x="840" y="393" font-size="11" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">5. CONSUMO ADMINISTRATIVO</text>
  <text x="840" y="419" font-size="16" font-weight="600" fill="#F5F3EC">Consola /mantenimiento</text>
  <text x="840" y="446" font-size="12" fill="#BDC4D1">• Protegida por X-Admin-Token (en memoria)</text>
  <text x="840" y="468" font-size="12" fill="#BDC4D1">• GET /api/admin/overview y /drift</text>
  <text x="840" y="490" font-size="12" fill="#BDC4D1">• POST /api/admin/health/probe</text>
  <text x="840" y="512" font-size="12" fill="#BDC4D1">• POST /api/admin/drift/evaluate</text>
  <text x="840" y="534" font-size="12" fill="#BDC4D1">• Vista de incidentes, almacenamiento R2</text>
  <text x="840" y="556" font-size="12" fill="#86D6B8">  y bandera de representatividad</text>

  <!-- Flechas -->
  <line x1="360" y1="210" x2="438" y2="310" stroke="#3156D3" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="360" y1="450" x2="438" y2="355" stroke="#3156D3" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="360" y1="490" x2="438" y2="490" stroke="#172B4D" stroke-width="1.8" marker-end="url(#arrDark)"/>
  <line x1="740" y1="490" x2="818" y2="230" stroke="#B57B14" stroke-width="2" marker-end="url(#arrAmber)"/>
  <line x1="740" y1="340" x2="818" y2="455" stroke="#3156D3" stroke-width="2" marker-end="url(#arrBlue)"/>
  <line x1="970" y1="331" x2="970" y2="363" stroke="#B57B14" stroke-width="2" marker-end="url(#arrAmber)"/>

  <text x="40" y="636" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Fuente: implementación local Doppler (services/api/src/maintenance/*, services/inference, scripts/drift_engine.py).</text>
</svg>
"""


def svg_figura_35_actualizacion_modelo() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1160 560" width="1160" height="560" font-family="IBM Plex Sans, sans-serif">
  <defs>
    <marker id="arrB" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#3156D3"/>
    </marker>
    <marker id="arrR" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#B8323B"/>
    </marker>
    <marker id="arrG" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#1F7A54"/>
    </marker>
  </defs>
  <rect width="1160" height="560" fill="#F5F3EC"/>
  <text x="40" y="42" font-size="22" font-weight="600" fill="#172B4D">Figura 35. Flujo controlado de validación, actualización y restauración automática del modelo</text>
  <text x="40" y="65" font-size="13" fill="#52617B">Empaquetado versionado, verificación offline en CPU, drenado de cola y rollback automático (scripts/model_manager.py) · Sección 10.2</text>

  <!-- Fila superior: pasos 1 a 4 -->
  <rect x="40" y="106" width="235" height="126" rx="12" fill="#FFFFFF" stroke="#172B4D" stroke-width="1.8"/>
  <text x="56" y="130" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#3156D3">PASO 1 · EMPAQUETADO</text>
  <text x="56" y="154" font-size="15" font-weight="600" fill="#172B4D">Paquete versionado</text>
  <text x="56" y="176" font-size="11.5" fill="#52617B">• model.pt + inference.json</text>
  <text x="56" y="194" font-size="11.5" fill="#52617B">• manifest.json + SHA-256</text>
  <text x="56" y="212" font-size="11.5" fill="#52617B">• Originales intocados</text>

  <rect x="315" y="106" width="245" height="126" rx="12" fill="#090F1D" stroke="#9BB1FF" stroke-width="2"/>
  <text x="331" y="130" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">PASO 2 · VALIDACIÓN OFFLINE</text>
  <text x="331" y="154" font-size="15" font-weight="600" fill="#F5F3EC">Contenedor sin red</text>
  <text x="331" y="176" font-size="11.5" fill="#BDC4D1">• docker --network none</text>
  <text x="331" y="194" font-size="11.5" fill="#BDC4D1">• Hashes + contrato + umbral</text>
  <text x="331" y="212" font-size="11.5" fill="#BDC4D1">• Carga strict=True + inferencia</text>

  <rect x="600" y="106" width="240" height="126" rx="12" fill="#FFFFFF" stroke="#3156D3" stroke-width="1.8"/>
  <text x="616" y="130" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#3156D3">PASO 3 · VENTANA SEGURA</text>
  <text x="616" y="154" font-size="15" font-weight="600" fill="#172B4D">Mantenimiento y drenado</text>
  <text x="616" y="176" font-size="11.5" fill="#52617B">• POST /admin/maintenance=true</text>
  <text x="616" y="194" font-size="11.5" fill="#52617B">• Nuevas cargas → HTTP 503</text>
  <text x="616" y="212" font-size="11.5" fill="#52617B">• Esperar analyzing_active = 0</text>

  <rect x="880" y="106" width="240" height="126" rx="12" fill="#FFFFFF" stroke="#3156D3" stroke-width="1.8"/>
  <text x="896" y="130" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#3156D3">PASO 4 · RESPALDO Y CAMBIO</text>
  <text x="896" y="154" font-size="15" font-weight="600" fill="#172B4D">Respaldo y reinicio</text>
  <text x="896" y="176" font-size="11.5" fill="#52617B">• Copia previa en models/backups/</text>
  <text x="896" y="194" font-size="11.5" fill="#52617B">• Actualiza models/active/</text>
  <text x="896" y="212" font-size="11.5" fill="#52617B">• docker compose restart inference</text>

  <!-- Fila inferior: Verificación + 2 ramas (Éxito vs Rollback) -->
  <rect x="600" y="295" width="240" height="126" rx="12" fill="#101B30" stroke="#F0C779" stroke-width="2"/>
  <text x="616" y="319" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#FFDF9F">PASO 5 · VERIFICACIÓN EN VIVO</text>
  <text x="616" y="343" font-size="15" font-weight="600" fill="#F5F3EC">Readiness y SHA-256</text>
  <text x="616" y="365" font-size="11.5" fill="#BDC4D1">• Comprobar /api/ready (HTTP 200)</text>
  <text x="616" y="383" font-size="11.5" fill="#BDC4D1">• Confirmar model_sha256 exacto</text>
  <text x="616" y="401" font-size="11.5" fill="#BDC4D1">• Confirmar contract_sha256 exacto</text>

  <rect x="880" y="295" width="240" height="126" rx="12" fill="#E3F5EA" stroke="#1F7A54" stroke-width="2"/>
  <text x="896" y="319" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#145334">CAMINO VERIFICADO</text>
  <text x="896" y="343" font-size="15" font-weight="600" fill="#145334">Servicio restaurado</text>
  <text x="896" y="365" font-size="11.5" fill="#145334">• maintenance = false</text>
  <text x="896" y="383" font-size="11.5" fill="#145334">• Registro en model_deployments</text>
  <text x="896" y="401" font-size="11.5" fill="#145334">• Cola reanudada normalmente</text>

  <rect x="40" y="295" width="490" height="126" rx="12" fill="#FDECEC" stroke="#B8323B" stroke-width="2"/>
  <text x="58" y="319" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#8F1D24">RAMAL DE CONTINGENCIA · RESTAURACIÓN AUTOMÁTICA (ROLLBACK)</text>
  <text x="58" y="343" font-size="15" font-weight="600" fill="#8F1D24">Rechazo previo o fallo de readiness/hash</text>
  <text x="58" y="366" font-size="11.5" fill="#8F1D24">• Si falla Paso 2: paquete rechazado antes de tocar el servicio (0 impacto).</text>
  <text x="58" y="385" font-size="11.5" fill="#8F1D24">• Si falla Paso 5: restaura models/backups/ → reinicia inference → verifica hash previo.</text>
  <text x="58" y="404" font-size="11.5" fill="#8F1D24">• Registra rollback/reject en model_deployments y desactiva mantenimiento.</text>

  <!-- Nota de honestidad -->
  <rect x="40" y="452" width="1080" height="58" rx="10" fill="#EAE8E1" stroke="#34435C" stroke-width="1"/>
  <text x="58" y="476" font-size="12" font-weight="600" fill="#172B4D">Alcance del ensayo controlado:</text>
  <text x="262" y="476" font-size="12" fill="#52617B">En el repositorio solo existe un checkpoint entrenado (v1.0.0-resnet18-baseline).</text>
  <text x="58" y="496" font-size="11.5" fill="#52617B">Los paquetes inválidos y corruptos se construyen en copias temporales aisladas; no existe un segundo modelo candidato real ni ganancia predictiva nueva.</text>

  <!-- Flechas -->
  <line x1="275" y1="169" x2="313" y2="169" stroke="#3156D3" stroke-width="2" marker-end="url(#arrB)"/>
  <line x1="560" y1="169" x2="598" y2="169" stroke="#3156D3" stroke-width="2" marker-end="url(#arrB)"/>
  <line x1="840" y1="169" x2="878" y2="169" stroke="#3156D3" stroke-width="2" marker-end="url(#arrB)"/>
  <path d="M 1000 232 L 1000 264 L 720 264 L 720 293" fill="none" stroke="#3156D3" stroke-width="2" marker-end="url(#arrB)"/>
  <line x1="840" y1="358" x2="878" y2="358" stroke="#1F7A54" stroke-width="2.2" marker-end="url(#arrG)"/>
  <line x1="600" y1="358" x2="532" y2="358" stroke="#B8323B" stroke-width="2.2" marker-end="url(#arrR)"/>
  <line x1="437" y1="232" x2="437" y2="293" stroke="#B8323B" stroke-width="1.8" stroke-dasharray="5 3" marker-end="url(#arrR)"/>

  <text x="40" y="542" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Fuente: implementación local Doppler (scripts/model_manager.py, /api/admin/maintenance, /api/admin/deployments).</text>
</svg>
"""


def svg_figura_36_retroalimentacion() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1160 560" width="1160" height="560" font-family="IBM Plex Sans, sans-serif">
  <defs>
    <marker id="aB" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#3156D3"/>
    </marker>
    <marker id="aD" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#172B4D"/>
    </marker>
  </defs>
  <rect width="1160" height="560" fill="#F5F3EC"/>
  <text x="40" y="42" font-size="22" font-weight="600" fill="#172B4D">Figura 36. Canal de retroalimentación del usuario y máquina de estados de revisión humana</text>
  <text x="40" y="65" font-size="13" fill="#52617B">Aislamiento por sesión HMAC, captura de metadatos de ventana, expiración de audio a 24 h y métricas deduplicadas · Sección 10.3</text>

  <!-- Bloque 1: Captura en Estudio -->
  <rect x="40" y="106" width="275" height="250" rx="14" fill="#090F1D" stroke="#9BB1FF" stroke-width="2"/>
  <text x="58" y="134" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#9BB1FF">1. ESTUDIO ACÚSTICO (SESIÓN HMAC)</text>
  <text x="58" y="158" font-size="15.5" font-weight="600" fill="#F5F3EC">FeedbackPanel.svelte</text>
  <text x="58" y="184" font-size="11.5" fill="#BDC4D1">Tipos admitidos:</text>
  <text x="58" y="204" font-size="11.5" fill="#FFDF9F">• false_alarm (ventana obligatoria)</text>
  <text x="58" y="224" font-size="11.5" fill="#FFDF9F">• missed_emergency (ventana oblig.)</text>
  <text x="58" y="244" font-size="11.5" fill="#BDC4D1">• technical_issue (general u opc.)</text>
  <text x="58" y="264" font-size="11.5" fill="#BDC4D1">• uncertain_or_other</text>
  <text x="58" y="294" font-size="11" fill="#86D6B8">POST /api/jobs/{id}/feedback</text>
  <text x="58" y="314" font-size="11" fill="#BDC4D1">• Verifica propiedad de sesión (404 ajena)</text>
  <text x="58" y="334" font-size="11" fill="#BDC4D1">• Cuota 30/h · instantánea score/umbral/SHA</text>

  <!-- Bloque 2: Máquina de estados -->
  <rect x="360" y="106" width="760" height="250" rx="14" fill="#FFFFFF" stroke="#3156D3" stroke-width="1.8"/>
  <text x="380" y="134" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#3156D3">2. MÁQUINA DE ESTADOS ESTRICTA EN SQLITE (PATCH /api/admin/feedback/{id} + feedback_events)</text>

  <!-- Estados -->
  <rect x="382" y="196" width="118" height="58" rx="10" fill="#EEF2FF" stroke="#3156D3" stroke-width="1.6"/>
  <text x="441" y="222" text-anchor="middle" font-size="13" font-weight="600" fill="#172B4D">received</text>
  <text x="441" y="240" text-anchor="middle" font-size="10.5" fill="#52617B">Recibido</text>

  <rect x="538" y="196" width="122" height="58" rx="10" fill="#101B30" stroke="#9BB1FF" stroke-width="1.8"/>
  <text x="599" y="222" text-anchor="middle" font-size="13" font-weight="600" fill="#F5F3EC">in_review</text>
  <text x="599" y="240" text-anchor="middle" font-size="10.5" fill="#BDC4D1">En revisión</text>

  <rect x="708" y="152" width="192" height="44" rx="8" fill="#E3F5EA" stroke="#1F7A54" stroke-width="1.6"/>
  <text x="804" y="179" text-anchor="middle" font-size="12.5" font-weight="600" fill="#145334">confirmed (etiqueta verif.)</text>

  <rect x="708" y="205" width="192" height="44" rx="8" fill="#EAE8E1" stroke="#52617B" stroke-width="1.6"/>
  <text x="804" y="232" text-anchor="middle" font-size="12.5" font-weight="600" fill="#172B4D">dismissed (descartado)</text>

  <rect x="708" y="258" width="192" height="44" rx="8" fill="#FEF4DF" stroke="#B57B14" stroke-width="1.6"/>
  <text x="804" y="285" text-anchor="middle" font-size="12" font-weight="600" fill="#744A00">insufficient_evidence</text>

  <rect x="955" y="196" width="140" height="58" rx="10" fill="#142E28" stroke="#86D6B8" stroke-width="1.8"/>
  <text x="1025" y="222" text-anchor="middle" font-size="13" font-weight="600" fill="#B6EFDA">resolved</text>
  <text x="1025" y="240" text-anchor="middle" font-size="10.5" fill="#86D6B8">Cerrado / auditado</text>

  <line x1="500" y1="225" x2="536" y2="225" stroke="#3156D3" stroke-width="2" marker-end="url(#aB)"/>
  <path d="M 660 212 L 684 212 L 684 174 L 706 174" fill="none" stroke="#3156D3" stroke-width="1.8" marker-end="url(#aB)"/>
  <line x1="660" y1="227" x2="706" y2="227" stroke="#3156D3" stroke-width="1.8" marker-end="url(#aB)"/>
  <path d="M 660 242 L 684 242 L 684 280 L 706 280" fill="none" stroke="#3156D3" stroke-width="1.8" marker-end="url(#aB)"/>
  <path d="M 900 174 L 928 174 L 928 214 L 953 214" fill="none" stroke="#172B4D" stroke-width="1.8" marker-end="url(#aD)"/>
  <line x1="900" y1="227" x2="953" y2="227" stroke="#172B4D" stroke-width="1.8" marker-end="url(#aD)"/>
  <path d="M 900 280 L 928 280 L 928 240 L 953 240" fill="none" stroke="#172B4D" stroke-width="1.8" marker-end="url(#aD)"/>

  <text x="382" y="334" font-size="11" font-family="IBM Plex Mono, monospace" fill="#8F1D24">Transiciones inválidas (ej. received → resolved) rechazadas con HTTP 409 Conflict</text>

  <!-- Bloque 3: Salvaguardas metodológicas y retención 24h -->
  <rect x="40" y="390" width="525" height="122" rx="12" fill="#EAE8E1" stroke="#34435C" stroke-width="1.2"/>
  <text x="58" y="416" font-size="11" font-family="IBM Plex Mono, monospace" fill="#172B4D">RETENCIÓN DE AUDIO (24 H) Y EVIDENCIA</text>
  <text x="58" y="440" font-size="12" fill="#52617B">• El archivo WAV en Cloudflare R2 se elimina tras 24 h (o al borrar el usuario).</text>
  <text x="58" y="460" font-size="12" fill="#52617B">• El panel muestra audio_currently_available; si ya expiró, la revisión usa</text>
  <text x="58" y="478" font-size="12" fill="#52617B">  el estado insufficient_evidence en lugar de inventar una verificación auditiva.</text>
  <text x="58" y="498" font-size="11.5" font-weight="600" fill="#172B4D">• Nunca se dispara reentrenamiento automático desde reportes de usuario.</text>

  <rect x="595" y="390" width="525" height="122" rx="12" fill="#FFFFFF" stroke="#B57B14" stroke-width="1.6"/>
  <text x="613" y="416" font-size="11" font-family="IBM Plex Mono, monospace" fill="#B57B14">MÉTRICAS SOBRE MUESTRA REVISADA (SESGADA)</text>
  <text x="613" y="440" font-size="12" fill="#52617B">• Deduplicación estricta por clave (job_id, window_index, model_sha256).</text>
  <text x="613" y="460" font-size="12" fill="#52617B">• Excluye casos UNCERTAIN y comentarios generales sin ventana.</text>
  <text x="613" y="480" font-size="12" fill="#52617B">• Si hay 0 ventanas verificadas → estado explícito «No disponibles» (unavailable).</text>
  <text x="613" y="498" font-size="11.5" font-weight="600" fill="#744A00">• Nunca equivale a exactitud global no sesgada del sistema.</text>

  <line x1="315" y1="225" x2="358" y2="225" stroke="#3156D3" stroke-width="2" marker-end="url(#aB)"/>

  <text x="40" y="542" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Fuente: implementación local Doppler (FeedbackPanel.svelte, /mantenimiento, services/api/src/maintenance/feedback.rs).</text>
</svg>
"""


def svg_drift_experiments_chart(exp_data: dict) -> str:
    raw_exps = exp_data.get("experiments", [])
    if isinstance(raw_exps, list):
        exps = {e["id"]: e.get("result", {}) for e in raw_exps if isinstance(e, dict) and "id" in e}
    else:
        exps = raw_exps
    e1 = exps.get("exp_1_control_comparable", {})
    e2 = exps.get("exp_2_cambios_controlados", {})
    features_e1 = {f["feature"]: f for f in e1.get("features", [])}
    features_e2 = {f["feature"]: f for f in e2.get("features", [])}

    ordered = [
        ("duration_seconds", "Duración (entrada)"),
        ("rms_before_normalization", "RMS entrada"),
        ("silence_ratio", "Silencio entrada"),
        ("logmel_mean", "Media Log-Mel"),
        ("spectral_centroid_hz", "Centroide esp."),
        ("score_mean", "Media score (salida)"),
        ("positive_window_ratio", "Tasa positiva (salida)"),
    ]
    rows = []
    for key, label in ordered:
        f1 = features_e1.get(key)
        f2 = features_e2.get(key)
        if f1 and f2:
            rows.append(
                (
                    label,
                    float(f1.get("normalized_statistic") or 0.0),
                    float(f2.get("normalized_statistic") or 0.0),
                    float(f2.get("threshold") or 1.0),
                    bool(f2.get("alerted")),
                )
            )
    if not rows:
        return ""

    max_val = max(max(v1, v2, thr) for _, v1, v2, thr, _ in rows) * 1.15
    max_val = max(max_val, 2.0)

    W, H = 1120, 560
    left, right, top, bottom = 230, 70, 105, 95
    plot_w = W - left - right
    plot_h = H - top - bottom
    row_h = plot_h / len(rows)

    bars = []
    for idx, (label, v1, v2, thr, alerted) in enumerate(rows):
        y0 = top + idx * row_h + 8
        bh = max(12, (row_h - 20) / 2)
        w1 = (v1 / max_val) * plot_w
        w2 = (v2 / max_val) * plot_w
        tx = left + (thr / max_val) * plot_w
        c2 = "#B8323B" if alerted else "#3156D3"
        lbl1_x = max(left + w1 + 6, tx + 8) if abs((left + w1 + 18) - tx) < 28 else (left + w1 + 6)
        bars.append(
            f'<text x="{left - 12}" y="{y0 + bh + 4:.1f}" text-anchor="end" font-size="12" fill="#172B4D">{esc(label)}</text>'
            f'<rect x="{left}" y="{y0:.1f}" width="{w1:.1f}" height="{bh:.1f}" rx="4" fill="#86D6B8" stroke="#1F7A54" stroke-width="1"/>'
            f'<rect x="{left}" y="{y0 + bh + 3:.1f}" width="{w2:.1f}" height="{bh:.1f}" rx="4" fill="{c2}"/>'
            f'<text x="{left + w2 + 6:.1f}" y="{y0 + 2*bh + 1:.1f}" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="{c2}">{v2:.2f}{" (ALERTA)" if alerted else ""}</text>'
            f'<line x1="{tx:.1f}" y1="{y0 - 3:.1f}" x2="{tx:.1f}" y2="{y0 + 2*bh + 6:.1f}" stroke="#172B4D" stroke-width="1.8" stroke-dasharray="3 2"/>'
            f'<text x="{lbl1_x:.1f}" y="{y0 + bh - 2:.1f}" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#145334">{v1:.2f}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="IBM Plex Sans, sans-serif">
  <rect width="{W}" height="{H}" fill="#F5F3EC"/>
  <text x="40" y="40" font-size="21" font-weight="600" fill="#172B4D">Experimentos controlados de drift: lote control vs lote desplazado (sintético)</text>
  <text x="40" y="62" font-size="12.5" fill="#52617B">Distancia Wasserstein 1D normalizada respecto a la referencia sintética congelada (seed_ref 20261001) · Línea punteada = umbral calibrado</text>
  <rect x="{left}" y="{top - 8}" width="{plot_w}" height="{plot_h + 16}" rx="8" fill="#FFFFFF" stroke="#D7D9DF"/>
  {''.join(bars)}
  <rect x="40" y="{H - 64}" width="14" height="14" rx="3" fill="#86D6B8" stroke="#1F7A54"/>
  <text x="60" y="{H - 52}" font-size="12" fill="#172B4D">Exp. 1: Lote control comparable (no_alert)</text>
  <rect x="360" y="{H - 64}" width="14" height="14" rx="3" fill="#B8323B"/>
  <text x="380" y="{H - 52}" font-size="12" fill="#172B4D">Exp. 2: Lote con cambios controlados (drift_detected)</text>
  <line x1="745" y1="{H - 57}" x2="775" y2="{H - 57}" stroke="#172B4D" stroke-width="2" stroke-dasharray="4 2"/>
  <text x="783" y="{H - 52}" font-size="12" fill="#172B4D">Umbral por variable (bootstrap p99)</text>
  <text x="40" y="{H - 22}" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Nota: validación metodológica sobre fixtures sintéticas; no sustituye un corpus real representativo (Sección 10.1).</text>
</svg>
"""


def svg_latencies_chart(overview: dict) -> str:
    lats = overview.get("latencies", {})
    stages = [
        ("Espera en cola", lats.get("queue_wait", {})),
        ("Descarga R2", lats.get("r2_fetch", {})),
        ("Prep. y Log-Mel", lats.get("decode_and_prepare", {})),
        ("Inferencia CPU", lats.get("inference", {})),
        ("Persistencia SQLite", lats.get("persist", {})),
        ("Total API", lats.get("total_processing", {})),
    ]
    rows = []
    for label, st in stages:
        p50 = float(st.get("p50_ms") or 0.0)
        p95 = float(st.get("p95_ms") or 0.0)
        n = int(st.get("n") or 0)
        rows.append((label, p50, p95, n))

    max_v = max((max(p50, p95) for _, p50, p95, _ in rows), default=10.0) * 1.18
    max_v = max(max_v, 10.0)

    W, H = 1120, 480
    left, right, top, bottom = 210, 80, 95, 85
    plot_w = W - left - right
    plot_h = H - top - bottom
    row_h = plot_h / len(rows)

    bars = []
    for idx, (label, p50, p95, n) in enumerate(rows):
        y0 = top + idx * row_h + 7
        bh = max(12, (row_h - 18) / 2)
        w50 = (p50 / max_v) * plot_w
        w95 = (p95 / max_v) * plot_w
        bars.append(
            f'<text x="{left - 12}" y="{y0 + bh + 4:.1f}" text-anchor="end" font-size="12" fill="#172B4D">{esc(label)} (n={n})</text>'
            f'<rect x="{left}" y="{y0:.1f}" width="{w50:.1f}" height="{bh:.1f}" rx="4" fill="#3156D3"/>'
            f'<text x="{left + w50 + 6:.1f}" y="{y0 + bh - 2:.1f}" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#172B4D">p50: {p50:.1f} ms</text>'
            f'<rect x="{left}" y="{y0 + bh + 3:.1f}" width="{w95:.1f}" height="{bh:.1f}" rx="4" fill="#F0C779" stroke="#B57B14"/>'
            f'<text x="{left + w95 + 6:.1f}" y="{y0 + 2*bh + 1:.1f}" font-size="10.5" font-family="IBM Plex Mono, monospace" fill="#744A00">p95: {p95:.1f} ms</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="IBM Plex Sans, sans-serif">
  <rect width="{W}" height="{H}" fill="#F5F3EC"/>
  <text x="40" y="40" font-size="21" font-weight="600" fill="#172B4D">Latencias por etapa en el historial desacoplado de monitoreo (30 días)</text>
  <text x="40" y="62" font-size="12.5" fill="#52617B">Validación local Linux Manjaro + Cloudflare R2 · Incluye persist_ms medido tras commit efectivo en SQLite</text>
  <rect x="{left}" y="{top - 8}" width="{plot_w}" height="{plot_h + 16}" rx="8" fill="#FFFFFF" stroke="#D7D9DF"/>
  {''.join(bars)}
  <rect x="40" y="{H - 54}" width="14" height="14" rx="3" fill="#3156D3"/>
  <text x="60" y="{H - 42}" font-size="12" fill="#172B4D">Mediana (p50)</text>
  <rect x="200" y="{H - 54}" width="14" height="14" rx="3" fill="#F0C779" stroke="#B57B14"/>
  <text x="220" y="{H - 42}" font-size="12" fill="#172B4D">Percentil 95 (p95)</text>
  <text x="40" y="{H - 18}" font-size="11" font-family="IBM Plex Mono, monospace" fill="#52617B">Fuente: /api/admin/overview (job_telemetry_history) · Mediciones de validación local, no SLA de producción.</text>
</svg>
"""


def write_academic_tables(run_dir: Path) -> None:
    tables_dir = run_dir / "tablas"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Tabla 44: Métricas y umbrales de monitoreo operativo y drift (10.1)
    t44_headers = [
        "Categoria",
        "Metrica",
        "Metodo_y_unidad",
        "Umbral_o_criterio",
        "Accion_esperada",
        "Estado_en_entrega",
    ]
    t44_rows = [
        [
            "Salud y disponibilidad",
            "Sonda periódica de dependencias (API, SQLite, Inferencia, R2)",
            "SELECT 1 + GET /ready + HeadBucket cada 60 s (ms)",
            "healthy / degraded / unavailable; 3 fallos consecutivos abre incidente",
            "HTTP 503 en /api/ready; apertura de incidente y cierre automático al recuperar",
            "Implementado y ejecutado (fallo controlado)",
        ],
        [
            "Latencia operativa",
            "p50/p95 por etapa (cola, R2, prep, inferencia, commit SQLite)",
            "Historial desacoplado 30 d (job_telemetry_history), ms y rangos de duración",
            "Seguimiento p50/p95 por rango (<10s, 10–30s, 30–60s, 60–120s)",
            "Detectar cuellos de botella de CPU, red R2 o contención SQLite",
            "Implementado y ejecutado en local",
        ],
        [
            "Cola y errores",
            "Profundidad de cola, tasa de errores de usuario vs internos, clips < 3 s",
            "Contadores SQLite desacoplados sin duplicados (UNIQUE job_id)",
            "Cola máx. 16 trabajos; concurrencia inferencia = 1",
            "Rechazo controlado HTTP 429/503 y diagnóstico separado usuario vs sistema",
            "Implementado y ejecutado",
        ],
        [
            "Almacenamiento y retención",
            "Tamaño SQLite (db+wal+shm), bytes/objetos en prefijo R2 y bitácora de purgas",
            "Metadatos FS + ListObjectsV2 acotado a R2_PREFIX + tabla retention_runs",
            "Audios/jobs 24 h; historial técnico 30 días; referencias drift conservadas",
            "Verificar que la purga automática no deje huérfanos en R2 ni borre historial 30 d",
            "Implementado y ejecutado",
        ],
        [
            "Drift de entrada (audio/espectro)",
            "Duración, SR, canales, pico, RMS, silencio, clipping, Log-Mel media/DE, centroide",
            "Wasserstein 1D normalizada y cambio de proporciones por archivo (n >= 20)",
            "Umbrales calibrados por bootstrap p99 con holgura (referencia congelada)",
            "Emitir alerta input_drift_detected y revisar fuentes/micrófonos de entrada",
            "Motor ejecutado con demo sintética; corpus real pendiente",
        ],
        [
            "Drift de salida (predicción)",
            "Media/máximo de score sigmoide por archivo y tasa de ventanas positivas",
            "Wasserstein 1D normalizada sobre salidas del mismo model_sha256",
            "Verificación estricta de compatibilidad (hash modelo + obs_v1); si difiere → evaluation_error",
            "Emitir alerta output_drift_detected y priorizar auditoría humana de ventanas",
            "Motor ejecutado con demo sintética; corpus real pendiente",
        ],
    ]

    # Tabla 45: Política y procedimiento de actualización periódica del modelo (10.2)
    t45_headers = [
        "Fase_o_cadencia",
        "Actividad",
        "Mecanismo_implementado",
        "Criterio_de_aceptacion_o_rechazo",
        "Alcance_en_validacion_local",
    ]
    t45_rows = [
        [
            "Empaquetado",
            "Construir paquete versionado inmutable",
            "models/packages/<version>/ con model.pt, inference.json y manifest.json",
            "Hashes SHA-256 obligatorios; carpeta original Doppler_Espectro_Brand_Kit intacta",
            "Ejecutado sobre v1.0.0-resnet18-baseline",
        ],
        [
            "Validación previa offline",
            "Verificar integridad, contrato y carga estricta CPU sin red",
            "scripts/model_manager.py validate (docker run --network none)",
            "Rechaza hash alterado, contrato/umbral inválido o state_dict incompatible antes de tocar producción",
            "Ejecutado (baseline aprobado + 3 paquetes inválidos en copias temporales rechazados)",
        ],
        [
            "Activación controlada",
            "Activar mantenimiento, drenar cola, respaldar, cambiar y reiniciar inference",
            "scripts/model_manager.py activate + POST /api/admin/maintenance",
            "Nuevas cargas → HTTP 503; analyzing_active = 0; /api/ready = 200 y SHA-256 exacto",
            "Ejecutado con reinicio real del contenedor inference",
        ],
        [
            "Restauración automática (rollback)",
            "Restaurar respaldo previo si falla readiness o hash esperado",
            "Rollback automático en model_manager.py + auditoría en model_deployments",
            "Vuelve al checkpoint previo sano, verifica /api/ready=200 y registra rollback",
            "Ejecutado con paquete corrupto temporal (restauración automática verificada)",
        ],
        [
            "Revisión operativa (diaria)",
            "Revisar salud, incidentes, cola, almacenamiento R2 y errores internos",
            "Consola /mantenimiento + GET /api/admin/overview",
            "Cero incidentes abiertos; retención 24 h sin errores R2",
            "Propuesta operativa soportada por consola real",
        ],
        [
            "Revisión semanal",
            "Revisar drift de entrada/salida y bandeja de retroalimentación",
            "Consola /mantenimiento (pestañas Drift y Retroalimentación)",
            "Triaje humano dentro de ventana 24 h cuando se requiera escucha del audio",
            "Propuesta operativa soportada por consola real",
        ],
        [
            "Revisión mensual / reentrenamiento",
            "Evaluar si el drift sostenido y casos confirmados justifican un candidato nuevo",
            "Entrenamiento offline fuera del servicio + validación paridad/métricas",
            "Nunca reentrenamiento automático; requiere evaluación offline en corpus real",
            "Política propuesta (sin segundo candidato entrenado en esta entrega)",
        ],
    ]

    # Tabla 46: Canal de retroalimentación del usuario y revisión humana (10.3)
    t46_headers = [
        "Dimension",
        "Especificacion",
        "Regla_de_seguridad_o_metodologia",
        "Verificacion_ejecutada",
    ]
    t46_rows = [
        [
            "Categorías de reporte",
            "false_alarm, missed_emergency, technical_issue, uncertain_or_other",
            "false_alarm y missed_emergency exigen window_index válido dentro del análisis",
            "Pruebas API (400 en índice inválido) + E2E en AudioStudio",
        ],
        [
            "Metadatos capturados",
            "job_id, window_index, label/score/umbral mostrados, intervalo, model_sha256, contract_sha256, audio_expires_at",
            "Instantánea inmutable tomada desde SQLite en el servidor; comentario limitado a 1000 caracteres",
            "Verificado en pruebas unitarias Rust e integración real",
        ],
        [
            "Aislamiento y cuotas",
            "Solo el propietario de la sesión HMAC puede reportar o consultar sus reportes",
            "Sesión ajena recibe HTTP 404; cuota de 30 reportes/hora por sesión; consola admin exige X-Admin-Token",
            "Verificado en integración (404 cruzado, 401 admin)",
        ],
        [
            "Retención 24 h de audio",
            "Indicadores audio_available_at_report y audio_currently_available calculados dinámicamente",
            "Tras purgar el WAV en R2/SQLite, la revisión se documenta como insufficient_evidence si no hubo escucha previa",
            "Verificado al eliminar trabajo y consultar /api/admin/feedback",
        ],
        [
            "Máquina de estados de revisión",
            "received → in_review → confirmed | dismissed | insufficient_evidence → resolved",
            "Transiciones fuera de orden rechazadas con HTTP 409; historial completo en feedback_events",
            "Verificado en tests Rust e integración real",
        ],
        [
            "Métricas sobre muestra revisada",
            "Ventanas verificadas deduplicadas por (job_id, window_index, model_sha256)",
            "Excluye UNCERTAIN y comentarios generales; muestra «No disponibles» si n=0; declarada muestra sesgada",
            "Verificado en unit tests Rust y panel /mantenimiento",
        ],
    ]

    def write_csv_and_md(stem: str, title: str, headers: list[str], rows: list[list[str]]) -> None:
        csv_path = tables_dir / f"{stem}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

        md_lines = [
            f"# {title}",
            "",
            "| " + " | ".join(h.replace("_", " ") for h in headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for r in rows:
            md_lines.append("| " + " | ".join(c.replace("|", "\\|") for c in r) + " |")
        (tables_dir / f"{stem}.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    write_csv_and_md(
        "tabla_44_metricas_umbrales_monitoreo_drift",
        "Tabla 44. Métricas operativas, de salud y de detección de drift en Doppler (Sección 10.1)",
        t44_headers,
        t44_rows,
    )
    write_csv_and_md(
        "tabla_45_politica_actualizacion_y_validacion_modelo",
        "Tabla 45. Procedimiento controlado de empaquetado, validación, actualización, rollback y cadencia de revisión (Sección 10.2)",
        t45_headers,
        t45_rows,
    )
    write_csv_and_md(
        "tabla_46_estados_campos_retroalimentacion",
        "Tabla 46. Especificación del canal de retroalimentación y revisión humana (Sección 10.3)",
        t46_headers,
        t46_rows,
    )


def convert_svgs_to_pngs(svg_paths: list[Path]) -> None:
    if not svg_paths:
        return
    js_script = """
const fs = require('fs');
const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  for (const svgPath of process.argv.slice(1)) {
    const svgText = fs.readFileSync(svgPath, 'utf-8');
    const wMatch = svgText.match(/width="(\\d+)"/);
    const hMatch = svgText.match(/height="(\\d+)"/);
    const w = wMatch ? parseInt(wMatch[1], 10) : 1160;
    const h = hMatch ? parseInt(hMatch[1], 10) : 600;
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<!doctype html><html><body style="margin:0;padding:0;background:transparent;">${svgText}</body></html>`);
    await page.screenshot({ path: svgPath.replace(/\\.svg$/, '.png'), fullPage: false });
  }
  await browser.close();
})();
"""
    proc = subprocess.run(
        ["node", "-e", js_script, *[str(p) for p in svg_paths]],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Error convirtiendo SVG a PNG con Playwright: {proc.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir: Path = args.run_dir

    fig_dir = run_dir / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)
    svgs: list[Path] = []

    for fname, content in [
        ("figura_34_arquitectura_monitoreo_y_drift.svg", svg_figura_34_monitoreo_drift()),
        ("figura_35_flujo_actualizacion_y_restauracion_modelo.svg", svg_figura_35_actualizacion_modelo()),
        ("figura_36_flujo_retroalimentacion_y_revision_humana.svg", svg_figura_36_retroalimentacion()),
    ]:
        p = fig_dir / fname
        p.write_text(content, encoding="utf-8")
        svgs.append(p)

    exp_path = run_dir / "experimentos_drift.json"
    if exp_path.is_file():
        svg = svg_drift_experiments_chart(json.loads(exp_path.read_text(encoding="utf-8")))
        if svg:
            p = fig_dir / "grafica_experimentos_drift.svg"
            p.write_text(svg, encoding="utf-8")
            svgs.append(p)

    overview_path = run_dir / "overview_operativo_raw.json"
    if overview_path.is_file():
        svg = svg_latencies_chart(json.loads(overview_path.read_text(encoding="utf-8")))
        if svg:
            p = fig_dir / "grafica_latencias_etapas_monitoreo.svg"
            p.write_text(svg, encoding="utf-8")
            svgs.append(p)

    convert_svgs_to_pngs(svgs)
    write_academic_tables(run_dir)
    print(f"Generadas {len(svgs)} figuras (SVG+PNG) y 3 tablas académicas (CSV+MD) en {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
