export const AVATAR_PX = 256;
const MAX_INPUT_BYTES = 15 * 1024 * 1024;

/** The centred square inside a width x height picture. */
export function squareCrop(width: number, height: number) {
  const side = Math.min(width, height);
  return { sx: Math.round((width - side) / 2), sy: Math.round((height - side) / 2), side };
}

/**
 * Centre-crops a picture to a square, scales it to 256 x 256 and returns it as a PNG. Drawing it
 * again on a canvas drops its EXIF data (location, camera), so none of that is uploaded.
 */
export async function prepareAvatar(file: File): Promise<Blob> {
  if (file.size > MAX_INPUT_BYTES) throw new Error("That picture is too large. Try a smaller one.");
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file); // also applies the photo's rotation
  } catch {
    throw new Error("That file is not a picture we can read. Use a PNG, JPEG or WebP picture.");
  }
  const { sx, sy, side } = squareCrop(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = AVATAR_PX;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("This browser cannot prepare pictures.");
  ctx.drawImage(bitmap, sx, sy, side, side, 0, 0, AVATAR_PX, AVATAR_PX);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("This browser cannot prepare pictures.");
  return blob;
}
