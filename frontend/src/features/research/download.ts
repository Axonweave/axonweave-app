/** Saves text as a file in the browser (CSV, Markdown, BibTeX ...). Nothing is sent anywhere. */
export function downloadText(name: string, text: string, mime = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** A safe file name stem from a user title. */
export function fileStem(title: string, fallback: string): string {
  return title.replace(/[^\w-]+/g, "_").slice(0, 60) || fallback;
}
