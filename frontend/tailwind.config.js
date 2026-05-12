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
        // MediFleet Cyan — blue-green clinical primary
        brand: {
          50:  '#ecfeff',
          100: '#cffafe',
          200: '#a5f3fc',
          300: '#67e8f9',
          400: '#22d3ee',
          500: '#06b6d4',
          600: '#0891b2', // Primary action
          700: '#0e7490',
          800: '#155e75',
          900: '#164e63',
          950: '#083344',
        },
        // Teal — secondary action / aurora bridge
        teal: {
          50:  '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488',
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
          950: '#042f2e',
        },
        // Emerald — success / confirmation
        accent: {
          50:  '#ecfdf5',
          100: '#d1fae5',
          200: '#a7f3d0',
          300: '#6ee7b7',
          400: '#34d399',
          500: '#10b981',
          600: '#059669',
          700: '#047857',
          800: '#065f46',
          900: '#064e3b',
        },
        // Calm clinical neutrals (slate-based ink scale)
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
        'soft':       '0 1px 2px 0 rgba(15, 23, 42, 0.04), 0 4px 16px -4px rgba(15, 23, 42, 0.08)',
        'elevated':   '0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 12px 32px -8px rgba(15, 23, 42, 0.14)',
        'glow':       '0 0 0 1px rgba(8, 145, 178, 0.18), 0 10px 32px -8px rgba(6, 182, 212, 0.45)',
        'glow-teal':  '0 0 0 1px rgba(20, 184, 166, 0.18), 0 10px 32px -8px rgba(45, 212, 191, 0.40)',
        'inner-line': 'inset 0 0 0 1px rgba(255, 255, 255, 0.06)',
      },
      backgroundImage: {
        // Cyan → Teal → Emerald — the signature MediFleet sweep
        'brand-gradient':  'linear-gradient(135deg, #0891b2 0%, #0d9488 50%, #059669 100%)',
        'brand-soft':      'linear-gradient(135deg, #67e8f9 0%, #5eead4 60%, #6ee7b7 100%)',
        'aurora':          'radial-gradient(at 18% 8%, rgba(34, 211, 238, 0.22) 0px, transparent 50%), radial-gradient(at 82% 92%, rgba(45, 212, 191, 0.18) 0px, transparent 50%), radial-gradient(at 50% 50%, rgba(16, 185, 129, 0.12) 0px, transparent 60%)',
        'grid-faint':      'linear-gradient(rgba(15, 23, 42, 0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(15, 23, 42, 0.04) 1px, transparent 1px)',
      },
      backgroundSize: {
        'grid-faint': '32px 32px',
      },
      keyframes: {
        'fade-in':        { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        'slide-up':       { '0%': { opacity: 0, transform: 'translateY(8px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        'slide-in-right': { '0%': { opacity: 0, transform: 'translateX(16px)' }, '100%': { opacity: 1, transform: 'translateX(0)' } },
        'pulse-soft':     { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.55 } },
        'float':          { '0%, 100%': { transform: 'translateY(0)' }, '50%': { transform: 'translateY(-6px)' } },
        'shimmer':        { '0%': { backgroundPosition: '-200% 0' }, '100%': { backgroundPosition: '200% 0' } },
      },
      animation: {
        'fade-in':        'fade-in 200ms ease-out',
        'slide-up':       'slide-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-in-right': 'slide-in-right 260ms cubic-bezier(0.16, 1, 0.3, 1)',
        'pulse-soft':     'pulse-soft 2.4s ease-in-out infinite',
        'float':          'float 6s ease-in-out infinite',
        'shimmer':        'shimmer 3s linear infinite',
      },
    },
  },
  plugins: [],
}
