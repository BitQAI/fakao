export function mdToHtml(md: string): string {
  return md
    .replace(/^##\s?(.*)$/gm, "<h3>$1</h3>")
    .replace(/^-\s?(.*)$/gm, "<li>$1</li>")
    .replace(/\n/g, "<br/>");
}
