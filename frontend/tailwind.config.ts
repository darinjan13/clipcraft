import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui'], mono: ['Geist Mono', 'ui-monospace', 'monospace'] },
      colors: {
        ink: '#e5e1e4',
        muted: '#a9a4b2',
        canvas: '#09090b',
        panel: '#131315',
        elevated: '#201f22',
        violet: '#a078ff',
        blue: '#0566d9',
      },
      boxShadow: {
        glass: '0 20px 70px rgba(0,0,0,.35), inset 0 1px rgba(255,255,255,.06)',
        glow: '0 0 40px rgba(139,92,246,.22)',
      },
      backgroundImage: {
        action: 'linear-gradient(135deg, #a078ff 0%, #6366f1 50%, #3b82f6 100%)',
        aurora: 'radial-gradient(circle at 20% 0%, rgba(139,92,246,.18), transparent 30%), radial-gradient(circle at 90% 20%, rgba(59,130,246,.12), transparent 30%)',
      },
    },
  },
  plugins: [],
} satisfies Config;
