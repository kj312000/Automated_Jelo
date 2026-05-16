/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0a0a0f',
          secondary: '#0f0f1a',
          panel: '#12121f',
          card: '#1a1a2e',
          border: '#1e1e35',
        },
        accent: {
          green: '#00ff88',
          red: '#ff3366',
          blue: '#00aaff',
          yellow: '#ffcc00',
          purple: '#aa00ff',
          orange: '#ff6600',
        },
        text: {
          primary: '#e0e0f0',
          secondary: '#8888aa',
          muted: '#555577',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Cascadia Code', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      animation: {
        pulse_fast: 'pulse 0.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        glow: 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          from: { boxShadow: '0 0 4px #00ff8844' },
          to: { boxShadow: '0 0 12px #00ff88aa' },
        },
      },
    },
  },
  plugins: [],
}
