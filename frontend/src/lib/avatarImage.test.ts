import { describe, expect, it, vi } from "vitest";
import { AVATAR_PX, prepareAvatar, squareCrop } from "@/lib/avatarImage";

describe("squareCrop", () => {
  it("takes the middle of a wide picture", () => {
    expect(squareCrop(400, 200)).toEqual({ sx: 100, sy: 0, side: 200 });
  });
  it("takes the middle of a tall picture", () => {
    expect(squareCrop(100, 300)).toEqual({ sx: 0, sy: 100, side: 100 });
  });
});

describe("prepareAvatar", () => {
  it("draws the centred square at 256 x 256 and exports a PNG", async () => {
    const drawImage = vi.fn();
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", async () => ({ width: 600, height: 400, close }));
    const toBlob = vi.fn((cb: BlobCallback, type?: string) =>
      cb(new Blob(["x"], { type: type ?? "" })),
    );
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage,
    } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(toBlob);

    const blob = await prepareAvatar(new File(["x"], "me.jpg", { type: "image/jpeg" }));

    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 100, 0, 400, 400, 0, 0, 256, 256);
    expect(toBlob.mock.calls[0]?.[1]).toBe("image/png");
    expect(blob.type).toBe("image/png");
    expect(AVATAR_PX).toBe(256);
    expect(close).toHaveBeenCalled();
  });

  it("says so when the file is not a picture", async () => {
    vi.stubGlobal("createImageBitmap", () => Promise.reject(new Error("bad")));
    await expect(prepareAvatar(new File(["x"], "me.txt"))).rejects.toThrow(/not a picture/);
  });
});
