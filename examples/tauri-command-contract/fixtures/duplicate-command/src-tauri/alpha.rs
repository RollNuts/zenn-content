#[tauri::command]
pub fn receipt_label(count: u32) -> String {
    format!("FIXTURE_BODY_TEXT_SHOULD_STAY_OUT_OF_GRAPH: {count}")
}

