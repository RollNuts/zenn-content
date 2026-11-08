import { invoke } from "@tauri-apps/api/core";

export async function requestLabel() {
  return invoke("receipt_label", { count: 3 });
}

