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
}: {
  provider?: string;
  process: "login" | "connect";
  label: string;
  returnTo?: string;
}) {
  const { data } = useProviders();
  if (!data?.some((p) => p.id === provider)) return null;
  return (
    <form
      method="post"
      action="/_allauth/browser/v1/auth/provider/redirect"
      onSubmit={() => returnTo && sessionStorage.setItem(RETURN_KEY, returnTo)}
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
