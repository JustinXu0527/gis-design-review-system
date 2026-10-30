import type { FileUploadPayload } from "@/api/client";

const SHAPEFILE_PARTS = new Set([".shp", ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".sbn", ".sbx"]);

export function isShapefilePart(filename: string): boolean {
  return SHAPEFILE_PARTS.has(fileExtension(filename));
}

export function normalizeProjectName(name: unknown): string {
  return String(name || "").replace(/\s+/g, " ").trim();
}

export function fileSelectionKey(files: File[] | Iterable<File> | null | undefined): string {
  return Array.from(files || [])
    .map((file) => `${file.name}:${file.size}:${file.lastModified}`)
    .join("|");
}

export async function filePayload(file: File): Promise<FileUploadPayload> {
  const buffer = await file.arrayBuffer();
  let binary = "";
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return { filename: file.name, content_base64: btoa(binary) };
}

export async function designUploadPayloads(files: File[]): Promise<FileUploadPayload[]> {
  const groups = new Map<string, File[]>();
  const payloads: FileUploadPayload[] = [];

  for (const file of files) {
    const ext = fileExtension(file.name);
    const stem = file.name.slice(0, file.name.length - ext.length);
    if (SHAPEFILE_PARTS.has(ext)) {
      if (!groups.has(stem)) groups.set(stem, []);
      groups.get(stem)?.push(file);
      continue;
    }
    payloads.push(await filePayload(file));
  }

  for (const [stem, group] of groups.entries()) {
    const hasShp = group.some((file) => fileExtension(file.name) === ".shp");
    if (!hasShp) continue;
    payloads.push({
      filename: `${stem}.zip`,
      files: await Promise.all(group.map(filePayload)),
    });
  }

  return payloads;
}

export function fileExtension(filename: string): string {
  const index = filename.lastIndexOf(".");
  return index >= 0 ? filename.slice(index).toLowerCase() : "";
}
