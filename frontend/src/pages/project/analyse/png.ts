// The light-mode values of the chart colours (index.css `.viz`), so a saved picture looks the
// same whatever theme the person was using.
const LIGHT: Record<string, string> = {
  "--viz-text": "#0b0b0b",
  "--viz-muted": "#52514e",
  "--viz-grid": "#e4e3df",
  "--viz-s1": "#2a78d6",
  "--viz-s2": "#eb6834",
  "--viz-s3": "#1baf7a",
};

/** Draw a chart's SVG onto a white canvas and return it as a PNG. */
export async function svgToPng(svg: SVGSVGElement): Promise<Blob> {
  const vb = svg.viewBox.baseVal;
  const w = vb.width || 480;
  const h = vb.height || 300;
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(w * 2));
  clone.setAttribute("height", String(h * 2));
  const text = new XMLSerializer()
    .serializeToString(clone)
    .replace(/var\((--viz-[a-z0-9]+)\)/g, (_m, k: string) => LIGHT[k] ?? "#000");
  const img = new Image();
  await new Promise<void>((ok, bad) => {
    img.onload = () => ok();
    img.onerror = () => bad(new Error("The chart could not be turned into a picture."));
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
  });
  const canvas = document.createElement("canvas");
  canvas.width = w * 2;
  canvas.height = h * 2;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("The chart could not be turned into a picture.");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);
  return new Promise((ok, bad) =>
    canvas.toBlob(
      (b) => (b ? ok(b) : bad(new Error("The chart could not be turned into a picture."))),
      "image/png",
    ),
  );
}
