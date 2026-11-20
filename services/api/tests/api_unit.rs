use doppler_api::domain::{
    merge_positive_intervals, sanitize_filename, sign_session_token, verify_session_token,
    WindowDto,
};

#[test]
fn session_token_sign_and_verify_roundtrip() {
    let secret = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    let session_id = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
    let signed = sign_session_token(session_id, secret);
    assert_eq!(verify_session_token(&signed, secret), Some(session_id.to_string()));
    assert_eq!(verify_session_token(&signed, "wrong_secret_0123456789abcdef0123"), None);
    assert_eq!(verify_session_token("tampered.deadbeef", secret), None);
}

#[test]
fn filename_sanitization_strips_paths_and_controls() {
    assert_eq!(sanitize_filename("../../etc/passwd.wav"), "passwd.wav");
    assert_eq!(sanitize_filename("C:\\fakepath\\sirena\x00test.wav"), "sirenatest.wav");
    assert_eq!(sanitize_filename("   "), "audio.wav");
}

#[test]
fn merge_positive_intervals_merges_overlapping_windows_accurately() {
    let windows = vec![
        WindowDto {
            index: 0,
            start_seconds: 0.0,
            end_seconds: 3.0,
            score: 0.2,
            label: "NON_EMERGENCY".into(),
            margin_vs_threshold: -0.45,
        },
        WindowDto {
            index: 1,
            start_seconds: 1.5,
            end_seconds: 4.5,
            score: 0.82,
            label: "EMERGENCY".into(),
            margin_vs_threshold: 0.16,
        },
        WindowDto {
            index: 2,
            start_seconds: 3.0,
            end_seconds: 6.0,
            score: 0.91,
            label: "EMERGENCY".into(),
            margin_vs_threshold: 0.25,
        },
        WindowDto {
            index: 3,
            start_seconds: 7.5,
            end_seconds: 10.5,
            score: 0.71,
            label: "EMERGENCY".into(),
            margin_vs_threshold: 0.05,
        },
    ];

    let (merged, coverage) = merge_positive_intervals(&windows);
    assert_eq!(merged.len(), 2);
    assert!((merged[0].start_seconds - 1.5).abs() < 1e-6);
    assert!((merged[0].end_seconds - 6.0).abs() < 1e-6);
    assert_eq!(merged[0].window_count, 2);
    assert!((merged[0].max_score - 0.91).abs() < 1e-6);
    assert!((merged[1].start_seconds - 7.5).abs() < 1e-6);
    assert!((merged[1].end_seconds - 10.5).abs() < 1e-6);
    assert!((coverage - 7.5).abs() < 1e-6);
}
