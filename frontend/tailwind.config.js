/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Dr. Kahura Medical Teal — refined for clinical clarity
        brand: {
          50:  '#ecfdf7',
          100: '#d1faec',
          200: '#a4f3d8',
          300: '#6de6bf',
          400: '#34d4a4',
          500: '#14b88e',
          600: '#0d9477', // Primary action
          700: '#0f7561', // Deep typography
          800: '#115e51',
          900: '#0f3d36',
          950: '#062520',
        },
        // Bright Emerald for success / confirmation
        accent: {
          50:  '#f0fdf4',
          100: '#dcfce7',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
        },
        // Calm clinical neutrals
        ink: {
          50:  '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
        slate: {
          850: '#111827',
        },
        surface: {
          DEFAULT: '#ffffff',
          muted:   '#f8fafc',
          subtle:  '#f1f5f9',
          dark:    '#0b1220',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        display: ['"Inter Display"', 'Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.04em' }],
      },
      letterSpacing: {
        'tightest': '-0.04em',
      },
      borderRadius: {
        'xl': '0.875rem',
        '2xl': '1.125rem',
        '3xl': '1.5rem',
      },
      boxShadow: {
        'soft':     '0 1px 2px 0 rgba(15, 23, 42, 0.04), 0 4px 16px -4px rgba(15, 23, 42, 0.08)',
        'elevated': '0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 12px 32px -8px rgba(15, 23, 42, 0.12)',
        'glow':     '0 0 0 1px rgba(20, 184, 142, 0.18), 0 8px 28px -6px rgba(20, 184, 142, 0.35)',
        'inner-line': 'inset 0 0 0 1px rgba(255, 255, 255, 0.06)',
      },
      backgroundImage: {
        'brand-gradient':  'linear-gradient(135deg, #0d9477 0%, #0f7561 50%, #115e51 100%)',
        'aurora':          'radial-gradient(at 20% 0%, rgba(45, 212, 191, 0.18) 0px, transparent 50%), radial-gradient(at 80% 100%, rgba(34, 197, 94, 0.16) 0px, transparent 50%)',
        'grid-faint':      'linear-gradient(rgba(15, 23, 42, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(15, 23, 42, 0.04) 1px, transparent 1px)',
      },
      backgroundSize: {
        'grid-faint': '32px 32px',
      },
      keyframes: {
        'fade-in':       { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        'slide-up':      { '0%': { opacity: 0, transform: 'translateY(8px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        'slide-in-right':{ '0%': { opacity: 0, transform: 'translateX(16px)' }, '100%': { opacity: 1, transform: 'translateX(0)' } },
        'pulse-soft':    { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.55 } },
      },
      animation: {
        'fade-in':         'fade-in 200ms ease-out',
        'slide-up':        'slide-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-in-right':  'slide-in-right 260ms cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-soft':      'pulse-soft 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
