use std::time::Duration;

use aws_credential_types::Credentials;
use aws_sdk_s3::config::{
    Region, RequestChecksumCalculation, ResponseChecksumValidation,
};
use aws_sdk_s3::presigning::PresigningConfig;
use aws_sdk_s3::Client;
use bytes::Bytes;

use crate::config::AppConfig;
use crate::error::ApiError;

#[derive(Debug, Clone)]
pub struct HeadObjectInfo {
    pub content_length: u64,
    pub etag: Option<String>,
    pub content_type: Option<String>,
}

#[derive(Clone)]
pub struct R2Storage {
    client: Client,
    bucket: String,
    prefix: String,
}

impl R2Storage {
    pub fn new(cfg: &AppConfig) -> Self {
        let creds = Credentials::new(
            cfg.r2_access_key_id.clone(),
            cfg.r2_secret_access_key.clone(),
            None,
            None,
            "doppler-r2-env",
        );

        let s3_config = aws_sdk_s3::Config::builder()
            .behavior_version_latest()
            .region(Region::new(cfg.r2_region.clone()))
            .endpoint_url(cfg.r2_endpoint.clone())
            .credentials_provider(creds)
            .force_path_style(true)
            .request_checksum_calculation(RequestChecksumCalculation::WhenRequired)
            .response_checksum_validation(ResponseChecksumValidation::WhenRequired)
            .build();

        let client = Client::from_conf(s3_config);
        Self {
            client,
            bucket: cfg.r2_bucket.clone(),
            prefix: cfg.r2_prefix.clone(),
        }
    }

    pub fn build_object_key(&self, session_id: &str, job_id: &str) -> String {
        format!("{}{session_id}/{job_id}.wav", self.prefix)
    }

    pub fn is_owned_key(&self, key: &str) -> bool {
        key.starts_with(&self.prefix) && !key.contains("..")
    }

    pub async fn presign_put(
        &self,
        key: &str,
        content_type: &str,
        ttl_seconds: u64,
    ) -> Result<String, ApiError> {
        if !self.is_owned_key(key) {
            return Err(ApiError::Validation("clave de objeto fuera del prefijo autorizado".into()));
        }
        let presign_cfg = PresigningConfig::expires_in(Duration::from_secs(ttl_seconds))
            .map_err(|e| ApiError::R2(format!("duración de firma PUT inválida: {e}")))?;

        let req = self
            .client
            .put_object()
            .bucket(&self.bucket)
            .key(key)
            .content_type(content_type)
            .presigned(presign_cfg)
            .await
            .map_err(|e| ApiError::R2(format!("no se pudo firmar PUT en R2: {e}")))?;

        Ok(req.uri().to_string())
    }

    pub async fn presign_get(&self, key: &str, ttl_seconds: u64) -> Result<String, ApiError> {
        if !self.is_owned_key(key) {
            return Err(ApiError::Validation("clave de objeto fuera del prefijo autorizado".into()));
        }
        let presign_cfg = PresigningConfig::expires_in(Duration::from_secs(ttl_seconds))
            .map_err(|e| ApiError::R2(format!("duración de firma GET inválida: {e}")))?;

        let req = self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .presigned(presign_cfg)
            .await
            .map_err(|e| ApiError::R2(format!("no se pudo firmar GET en R2: {e}")))?;

        Ok(req.uri().to_string())
    }

    pub async fn head_object(&self, key: &str) -> Result<Option<HeadObjectInfo>, ApiError> {
        if !self.is_owned_key(key) {
            return Err(ApiError::Validation("clave de objeto fuera del prefijo autorizado".into()));
        }
        match self
            .client
            .head_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
        {
            Ok(out) => {
                let len = u64::try_from(out.content_length().unwrap_or(0)).unwrap_or(0);
                Ok(Some(HeadObjectInfo {
                    content_length: len,
                    etag: out.e_tag().map(|s| s.to_string()),
                    content_type: out.content_type().map(|s| s.to_string()),
                }))
            }
            Err(sdk_err) => {
                let is_not_found = sdk_err
                    .raw_response()
                    .map(|r| r.status().as_u16() == 404)
                    .unwrap_or(false)
                    || sdk_err
                        .as_service_error()
                        .map(|se| se.is_not_found())
                        .unwrap_or(false);
                if is_not_found {
                    Ok(None)
                } else {
                    Err(ApiError::R2(format!("falló HeadObject en R2: {sdk_err}")))
                }
            }
        }
    }

    pub async fn download_bounded(&self, key: &str, max_bytes: u64) -> Result<Bytes, ApiError> {
        if !self.is_owned_key(key) {
            return Err(ApiError::Validation("clave de objeto fuera del prefijo autorizado".into()));
        }
        let mut resp = self
            .client
            .get_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| ApiError::R2(format!("no se pudo descargar el objeto de R2: {e}")))?;

        if let Some(cl) = resp.content_length() {
            if cl < 0 || (cl as u64) > max_bytes {
                return Err(ApiError::LimitExceeded(format!(
                    "el objeto en R2 ({cl} bytes) excede el máximo de {max_bytes} bytes"
                )));
            }
        }

        let cap = resp
            .content_length()
            .and_then(|v| usize::try_from(v).ok())
            .map(|v| v.min(max_bytes as usize))
            .unwrap_or(64 * 1024);
        let mut out = Vec::with_capacity(cap);

        while let Some(chunk) = resp
            .body
            .try_next()
            .await
            .map_err(|e| ApiError::R2(format!("error leyendo flujo de R2: {e}")))?
        {
            if (out.len() as u64).saturating_add(chunk.len() as u64) > max_bytes {
                return Err(ApiError::LimitExceeded(format!(
                    "la descarga desde R2 superó el límite de {max_bytes} bytes"
                )));
            }
            out.extend_from_slice(&chunk);
        }

        Ok(Bytes::from(out))
    }

    pub async fn delete_object(&self, key: &str) -> Result<(), ApiError> {
        if !self.is_owned_key(key) {
            return Err(ApiError::Validation("clave de objeto fuera del prefijo autorizado".into()));
        }
        self.client
            .delete_object()
            .bucket(&self.bucket)
            .key(key)
            .send()
            .await
            .map_err(|e| ApiError::R2(format!("no se pudo eliminar el objeto en R2: {e}")))?;
        Ok(())
    }

    pub async fn check_bucket_reachable(&self) -> Result<(), ApiError> {
        self.client
            .head_bucket()
            .bucket(&self.bucket)
            .send()
            .await
            .map_err(|e| ApiError::R2(format!("bucket R2 inaccesible: {e}")))?;
        Ok(())
    }
}
