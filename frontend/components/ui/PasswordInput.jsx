"use client";

// A password field with an eye button that reveals what was typed — the
// usual cure for a mistyped password on a phone keyboard. The button never
// submits the form and keeps the input's own props (autoComplete,
// minLength, required…) untouched.
import { forwardRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { useI18n } from "@/app/providers/I18nProvider";

const PasswordInput = forwardRef(function PasswordInput({ className = "", ...props }, ref) {
  const { t } = useI18n();
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <input ref={ref} type={shown ? "text" : "password"} className={`${className} pe-11`} {...props} />
      <button
        type="button"
        onClick={() => setShown((value) => !value)}
        aria-label={t(shown ? "auth.hidePassword" : "auth.showPassword")}
        title={t(shown ? "auth.hidePassword" : "auth.showPassword")}
        aria-pressed={shown}
        className="tap absolute inset-y-0 end-2 my-auto grid h-8 w-8 place-items-center rounded-control text-muted hover:bg-paper hover:text-ink"
      >
        {shown ? <EyeOff size={17} /> : <Eye size={17} />}
      </button>
    </div>
  );
});

export default PasswordInput;
