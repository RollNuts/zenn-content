import { invoke } from "@tauri-apps/api/core";

const command = "receipt_label";

export async function requestLabel() {
  return invoke(command, { count: 3 });
}

