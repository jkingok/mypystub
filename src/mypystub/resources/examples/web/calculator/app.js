const bill = document.getElementById("bill");
const pct = document.getElementById("pct");
const out = document.getElementById("out");
function update() {
  const tip = (bill.value * pct.value) / 100;
  out.textContent = `Tip ${tip.toFixed(2)}, total ${(+bill.value + tip).toFixed(2)}`;
}
bill.oninput = pct.oninput = update;
update();
