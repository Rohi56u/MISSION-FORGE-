/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: {
          DEFAULT: '#05080E',
          bg: '#05080E',
        },
        panel: {
          DEFAULT: '#0B0F17',
          surface: '#0B0F17',
          raised: '#111827',
        },
        hairline: {
          DEFAULT: '#1E293B',
          border: '#1E293B',
        },
        accent: {
          DEFAULT: '#0284C7',
          hover: '#0369A1',
          subtle: 'rgba(2, 132, 199, 0.15)',
        },
        status: {
          nominal: '#10B981',
          caution: '#F59E0B',
          alert: '#EF4444',
          inactive: '#64748B',
        },
      },
      fontFamily: {
        mono: [
          'Geist Mono',
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
        sans: [
          'Inter',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
      },
      boxShadow: {
        'panel': '0 1px 3px 0 rgba(0, 0, 0, 0.4)',
      },
    },
  },
  plugins: [],
};
