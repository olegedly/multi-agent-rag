/* @refresh reload */
import './index.css';
import './theme/theme.css';
import { initTheme } from './theme/theme';
import { render } from 'solid-js/web';

import App from './App';

// Theme init — runs synchronously to avoid FOUC
initTheme();

const root = document.getElementById('root');

if (import.meta.env.DEV && !(root instanceof HTMLElement)) {
  throw new Error(
    'Root element not found. Did you forget to add it to your index.html? Or maybe the id attribute got misspelled?',
  );
}

render(() => <App />, root!);
