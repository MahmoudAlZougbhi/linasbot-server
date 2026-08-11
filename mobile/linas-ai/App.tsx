import { LanguageProvider } from './src/i18n/LanguageContext';
import { ThemeProvider } from './src/theme';
import { AppShell } from './src/app/AppShell';

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <AppShell />
      </LanguageProvider>
    </ThemeProvider>
  );
}
