// Two-decimal rounding that agrees with the server.
//
// The API rounds half-up on exact decimals (Decimal ROUND_HALF_UP). Rounding
// binary floats directly does not: 10.075 is stored as 10.07499999…, so
// Math.round(10.075 * 100) gives 1007 and the till asked for 0.01 less than
// the invoice — which the server then read as an unpaid balance, i.e. a
// credit sale, and refused without a named customer. Trimming the float
// noise with toPrecision(12) first recovers the decimal the cashier sees.
export function round2(value) {
  const n = Number(value) || 0;
  const cents = Math.round(Number((Math.abs(n) * 100).toPrecision(12)));
  return (Math.sign(n) * cents) / 100;
}
