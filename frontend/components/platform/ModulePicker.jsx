"use client";

// Checkboxes for a plan version's modules, one per code the backend knows,
// with an "all modules" switch. Dependencies are kept consistent as the
// user clicks (returns need sales/purchasing + inventory).
import { useI18n } from "@/app/providers/I18nProvider";
import { ALL_MODULES, CORE_MODULES, MODULE_DEPENDENCIES, PLAN_MODULES, moduleLabel, toggleModule } from "@/lib/planModules";

export { moduleLabel };

export default function ModulePicker({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  const all = value.includes(ALL_MODULES);
  const selected = all ? PLAN_MODULES : value;
  return (
    <div className="rounded-control border border-line bg-paper/60 p-3">
      <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          checked={all}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked ? [ALL_MODULES] : [])}
          className="h-4 w-4 accent-accent"
        />
        {t("platformPlans.allModules")}
      </label>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {PLAN_MODULES.filter((code) => !CORE_MODULES.includes(code)).map((code) => {
          const needs = MODULE_DEPENDENCIES[code];
          return (
            <label key={code} className={`flex cursor-pointer items-start gap-2 text-sm ${all ? "opacity-60" : ""}`}>
              <input
                type="checkbox"
                checked={selected.includes(code)}
                disabled={disabled || all}
                onChange={() => onChange(toggleModule(value, code))}
                className="mt-0.5 h-4 w-4 accent-accent"
              />
              <span>
                {moduleLabel(code, t)}
                <span className="block text-xs text-muted" dir="ltr">{code}{needs ? ` · ${t("platformPlans.requires", { modules: needs.map((need) => moduleLabel(need, t)).join(", ") })}` : ""}</span>
              </span>
            </label>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted">{t("platformPlans.coreIncluded", { modules: CORE_MODULES.map((code) => moduleLabel(code, t)).join("، ") })}</p>
      {!all && selected.filter((code) => !CORE_MODULES.includes(code)).length === 0 && <p className="mt-2 text-xs text-danger">{t("platformPlans.modulesRequired")}</p>}
    </div>
  );
}
