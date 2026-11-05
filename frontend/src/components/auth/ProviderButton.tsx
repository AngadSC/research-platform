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
      <Button type="submit" variant="outline" className="w-full">
        {label}
      </Button>
    </form>
  );
}
