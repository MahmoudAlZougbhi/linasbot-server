import '@testing-library/jest-dom/vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

global.ResizeObserver = global.ResizeObserver || ResizeObserverStub;

Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || function scrollIntoView() {};
