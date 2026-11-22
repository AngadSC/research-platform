import { Button } from "@/components/ui/button";
import { useProviders } from "@/hooks/auth";
import { getCookie } from "@/lib/api";

export const CALLBACK_URL = "/account/provider/callback";
export const RETURN_KEY = "oauth_return";

/** Starts the provider flow with a native form POST (allauth answers with a redirect). Hidden without the provider. */
export function ProviderButton({
  provider = "google",
  process,
  label,
  returnTo,
  beforeSubmit,
}: {
  provider?: string;
  process: "login" | "connect";
  label: string;
  returnTo?: string;
  /** Runs before the page leaves (e.g. reauthentication); the form posts once it resolves. */
  beforeSubmit?: () => Promise<void>;
}) {
  const { data } = useProviders();
  if (!data?.some((p) => p.id === provider)) return null;
  return (
    <form
      method="post"
      action="/_allauth/browser/v1/auth/provider/redirect"
      onSubmit={(e) => {
        if (returnTo) sessionStorage.setItem(RETURN_KEY, returnTo);
        if (!beforeSubmit) return;
        e.preventDefault();
        const form = e.currentTarget;
        beforeSubmit().then(
          () => form.submit(),
          () => undefined, // cancelled
        );
      }}
    >
      <input type="hidden" name="provider" value={provider} />
      <input type="hidden" name="process" value={process} />
      <input type="hidden" name="callback_url" value={CALLBACK_URL} />
      <input type="hidden" name="csrfmiddlewaretoken" value={getCookie("csrftoken") ?? ""} />
      {provider === "google" ? (
        // Google sign-in branding: https://developers.google.com/identity/branding-guidelines
        <button
          type="submit"
          className="flex h-10 w-full items-center justify-center gap-2.5 rounded-full border border-[#747775] bg-white py-0 pr-3 pl-3 text-sm font-medium text-[#1f1f1f] hover:bg-[#f8f8f8] focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none dark:border-[#8e918f] dark:bg-[#131314] dark:text-[#e3e3e3] dark:hover:bg-[#1c1c1d]"
        >
          <span className="flex size-[18px] items-center justify-center rounded-full bg-white">
            <svg
              viewBox="0 0 48 48"
              className="size-[18px]"
              aria-hidden="true"
              data-testid="google-logo"
            >
              <path
                fill="#EA4335"
                d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
              />
              <path
                fill="#4285F4"
                d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
              />
              <path
                fill="#FBBC05"
                d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
              />
              <path
                fill="#34A853"
                d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
              />
            </svg>
          </span>
          {label}
        </button>
      ) : (
        <Button type="submit" variant="outline" className="w-full">
          {label}
        </Button>
      )}
    </form>
  );
}
