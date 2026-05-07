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
        // Dr. Kahura Medical Teal
        brand: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          300: '#5eead4',
          400: '#2dd4bf',
          500: '#14b8a6',
          600: '#0d9488', // Main teal (Matches website overlay)
          700: '#0f766e', // Deep teal for typography/logos
          800: '#115e59',
          900: '#134e4a', // Deepest background gradient tone
        },
        // Bright Emerald for Action Buttons
        accent: {
          500: '#22c55e', // Matches the WhatsApp green
          600: '#16a34a',
        },
        slate: {
          850: '#111827', // A deeper, richer dark mode slate for the sidebar
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        'soft': '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
      }
    },
  },
  plugins: [],
}