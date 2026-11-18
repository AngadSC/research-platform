import { useEffect, useState } from "react";

const PHONE = "(max-width: 639px)"; // Tailwind's sm breakpoint

/** True below the sm breakpoint; false where matchMedia is missing (tests). */
export function useIsPhone() {
  const [phone, setPhone] = useState(() => !!window.matchMedia?.(PHONE).matches);
  useEffect(() => {
    const mq = window.matchMedia?.(PHONE);
    if (!mq) return;
    const on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return phone;
}
