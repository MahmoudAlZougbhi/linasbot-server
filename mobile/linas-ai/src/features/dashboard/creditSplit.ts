export function splitCreditRemaining(input: {
  included?: number | null;
  purchased?: number | null;
  available?: number | null;
  reserved?: number | null;
}): { membership: number; bought: number } {
  const included = Math.max(0, Number(input.included) || 0);
  const purchased = Math.max(0, Number(input.purchased) || 0);
  const available = Math.max(0, Number(input.available) || 0);
  const reserved = Math.max(0, Number(input.reserved) || 0);
  const pool = included + purchased;
  const used = pool > 0 ? Math.max(0, pool - available - reserved) : 0;
  let membership = included - Math.min(used, included);
  if (membership > available) membership = available;
  return { membership, bought: available - membership };
}
