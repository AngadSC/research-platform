import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { UserAvatar } from "@/components/shared/UserAvatar";
import { render } from "@testing-library/react";
import { makeLab, mockFetch, renderRoute, SESSION, signedIn } from "@/test/utils";

const toastSuccess = vi.hoisted(() => vi.fn());
const toastError = vi.hoisted(() => vi.fn());
vi.mock("sonner", async (orig) => ({
  ...(await orig<typeof import("sonner")>()),
  toast: { success: toastSuccess, error: toastError },
}));

vi.mock("@/lib/avatarImage", () => ({
  prepareAvatar: vi.fn(async (f: File) => {
    if (f.name === "notes.txt") throw new Error("That file is not a picture we can read.");
    return new Blob(["png"], { type: "image/png" });
  }),
}));

const me = {
  id: "u1",
  email: "ada@uni.edu",
  display_name: "Ada Byron",
  pronouns: "",
  bio: "",
  avatar_url: null as string | null,
  preferences: {},
};

function world(extra: Record<string, unknown> = {}) {
  return {
    [SESSION]: signedIn,
    "GET /api/me/": { body: me },
    "PATCH /api/me/": (req: { body: unknown }) => ({ body: { ...me, ...(req.body as object) } }),
    "GET /api/labs/": { body: [makeLab(["view_lab"])] },
    ...extra,
  } as Parameters<typeof mockFetch>[0];
}

describe("profile", () => {
  beforeEach(() => {
    toastSuccess.mockClear();
    localStorage.clear();
    URL.createObjectURL = () => "blob:preview";
    URL.revokeObjectURL = () => undefined;
  });

  it("saves name, pronouns and bio, and counts the bio", async () => {
    const calls = mockFetch(world());
    renderRoute("/settings#profile");
    const pronouns = await screen.findByLabelText("Pronouns");
    expect(pronouns).toHaveAttribute("placeholder", "she/her, he/him, they/them");
    await userEvent.type(pronouns, "they/them");
    await userEvent.type(screen.getByLabelText("Bio"), "I study sleep.");
    expect(screen.getByText("14 / 500")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Profile saved"));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      display_name: "Ada Byron",
      pronouns: "they/them",
      bio: "I study sleep.",
    });
  });

  it("previews a chosen picture, uploads it on Save, and lets you drop one", async () => {
    const calls = mockFetch(
      world({
        "PUT /api/me/avatar/": { body: { ...me, avatar_url: "/api/users/u1/avatar/?v=1" } },
      }),
    );
    renderRoute("/settings#profile");
    const picture = await screen.findByLabelText("Profile picture file");
    await userEvent.upload(picture, new File(["x"], "me.jpg", { type: "image/jpeg" }));
    expect(await screen.findByText(/Press Save to keep it/)).toBeInTheDocument();
    expect(document.querySelector("img[src='blob:preview']")).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Profile saved"));
    const put = calls.find((c) => c.method === "PUT");
    expect((put?.body as FormData).get("file")).toBeInstanceOf(Blob);

    // dropping a file stages it too
    const zone = screen
      .getByRole("button", { name: /^(Choose a|Change) picture$/ })
      .closest("div[class*=border-dashed]")!;
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(["x"], "b.png", { type: "image/png" })] },
    });
    expect(await screen.findByText(/Press Save to keep it/)).toBeInTheDocument();
  });

  it("says plainly when the file is not a picture", async () => {
    mockFetch(world());
    renderRoute("/settings#profile");
    const picture = await screen.findByLabelText("Profile picture file");
    fireEvent.change(picture, { target: { files: [new File(["x"], "notes.txt")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("not a picture we can read");
  });

  it("removes the saved picture", async () => {
    const calls = mockFetch(
      world({
        "GET /api/me/": { body: { ...me, avatar_url: "/api/users/u1/avatar/?v=1" } },
        "DELETE /api/me/avatar/": { status: 204 },
      }),
    );
    renderRoute("/settings#profile");
    await userEvent.click(await screen.findByRole("button", { name: "Remove" }));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith("Picture removed"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  });
});

describe("UserAvatar", () => {
  it("shows the picture when there is one, else initials", () => {
    const { container, rerender } = render(
      <UserAvatar user={{ email: "a@x.test", display_name: "Lee Lead", avatar_url: "/p.png" }} />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", "/p.png");
    rerender(<UserAvatar user={{ email: "a@x.test", display_name: "Lee Lead" }} />);
    expect(container).toHaveTextContent("LL");
  });

  it("falls back to initials when the picture fails to load", () => {
    const { container } = render(
      <UserAvatar
        user={{ email: "a@x.test", display_name: "Lee Lead", avatar_url: "/gone.png" }}
      />,
    );
    fireEvent.error(container.querySelector("img")!);
    expect(container).toHaveTextContent("LL");
  });
});
