// Categories the system writes itself (payroll postings, salary advances,
// petty cash from the till) are stored in English so reports group them as
// one line; a person reading an Arabic screen sees them in Arabic. Any
// category a user typed is shown as typed.
const SYSTEM = {
  Payroll: "finance.systemCategory.payroll",
  "Salary advances": "finance.systemCategory.salaryAdvances",
  "Petty cash": "finance.systemCategory.pettyCash",
};

export function expenseCategory(name, t) {
  const key = SYSTEM[name];
  return key ? t(key) : name;
}
