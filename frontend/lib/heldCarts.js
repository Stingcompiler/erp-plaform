import { storageKey } from "./localIdentity.js";
function prefix() { return `${storageKey("heldCart")}:`; }
export const heldCarts = {
  list() {
    const p = prefix(), rows = [];
    for (let i=0; i<localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(p)) rows.push(JSON.parse(localStorage.getItem(key)));
    }
    return rows.sort((a,b) => b.saved_at-a.saved_at);
  },
  save(cart) {
    const row = { ...cart, id: cart.id || crypto.randomUUID(), saved_at: Date.now() };
    localStorage.setItem(prefix()+row.id, JSON.stringify(row));
    return row;
  },
  remove(id) { if (id) localStorage.removeItem(prefix()+id); },
};
