// Mirrors CompanyBankAccount.CHANNEL_CHOICES on the server. In Sudan most
// customer transfers arrive through a bank's app rather than a branch.
export const BANK_CHANNELS = ["bank", "bankak", "fawri", "ocash", "wallet"];

export function channelLabel(t, channel) {
  return t(`sales.channels.${BANK_CHANNELS.includes(channel) ? channel : "bank"}`);
}

/** "Bankak · Bank of Khartoum · Alpha Trading" for pickers. */
export function accountLabel(t, account) {
  if (!account) return "";
  const parts = [account.bank_name, account.account_name].filter(Boolean);
  if (account.channel && account.channel !== "bank") parts.unshift(channelLabel(t, account.channel));
  return parts.join(" · ");
}
