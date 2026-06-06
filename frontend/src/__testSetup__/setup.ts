// Override Node.js v26's half-baked built-in localStorage with a working mock
const store = new Map<string, string>();

const mockLocalStorage: Storage = {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => {
    store.set(key, value);
  },
  removeItem: (key: string) => {
    store.delete(key);
  },
  clear: () => {
    store.clear();
  },
  get length() {
    return store.size;
  },
  key: (index: number) => [...store.keys()][index] ?? null,
};

Object.defineProperty(globalThis, "localStorage", {
  value: mockLocalStorage,
  writable: false,
  configurable: true,
});

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {};
