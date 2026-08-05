/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Cairo", "Tajawal", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#f0f9f9",
          100: "#d9f2f2",
          200: "#b5e5e5",
          300: "#80cfcf",
          400: "#4cb3b3",
          500: "#339999", // Calming Teal
          600: "#267a7a",
          700: "#226363",
          800: "#205050",
          900: "#1e4444",
        },
        priority: {
          1: "#ef4444", // Severe alert red
          2: "#f59e0b", // Specialist warning amber
          3: "#3b82f6", // Monitoring blue
        }
      }
    },
  },
  plugins: [],
}
