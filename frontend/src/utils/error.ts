export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error || "操作失败");
}
