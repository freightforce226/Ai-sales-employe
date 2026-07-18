/**
 * Purpose: Centrally defines typescript-based design tokens for FreightForce AI.
 * Responsibility: Outlining the 8pt spacing system, radius presets, soft shadows, z-index layers, typography configurations, and animation durations.
 */

export const spacing = {
  "2xs": "4px",    // 0.25rem
  xs: "8px",       // 0.5rem
  sm: "12px",      // 0.75rem
  md: "16px",      // 1rem
  lg: "20px",      // 1.25rem
  xl: "24px",      // 1.5rem
  "2xl": "32px",   // 2rem
  "3xl": "40px",   // 2.5rem
  "4xl": "48px",   // 3rem
  "5xl": "64px",   // 4rem
} as const;

export const radius = {
  none: "0px",
  xs: "4px",
  sm: "6px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  "2xl": "20px",
  full: "9999px",
} as const;

export const shadow = {
  none: "none",
  // Extremely soft, low-contrast shadows matching Stripe/Linear aesthetics
  sm: "0 1px 2px 0 rgba(0, 0, 0, 0.03)",
  md: "0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -2px rgba(0, 0, 0, 0.03)",
  lg: "0 10px 15px -3px rgba(0, 0, 0, 0.03), 0 4px 6px -4px rgba(0, 0, 0, 0.03)",
  xl: "0 20px 25px -5px rgba(0, 0, 0, 0.04), 0 8px 10px -6px rgba(0, 0, 0, 0.04)",
  focus: "0 0 0 3px rgba(37, 99, 235, 0.15)",
} as const;

export const typography = {
  fontFamily: "Inter Variable, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  scale: {
    display: { fontSize: "36px", lineHeight: "44px", fontWeight: "700", letterSpacing: "-0.02em" },
    heading: { fontSize: "24px", lineHeight: "32px", fontWeight: "700", letterSpacing: "-0.015em" },
    title: { fontSize: "20px", lineHeight: "28px", fontWeight: "600", letterSpacing: "-0.01em" },
    subtitle: { fontSize: "16px", lineHeight: "24px", fontWeight: "500", letterSpacing: "-0.005em" },
    body: { fontSize: "14px", lineHeight: "20px", fontWeight: "500", letterSpacing: "0" },
    caption: { fontSize: "12px", lineHeight: "16px", fontWeight: "500", letterSpacing: "0.005em" },
    label: { fontSize: "11px", lineHeight: "14px", fontWeight: "600", letterSpacing: "0.02em" },
    mono: { fontSize: "13px", lineHeight: "18px", fontFamily: "monospace", letterSpacing: "0" },
  },
} as const;

export const duration = {
  fast: "120ms",
  normal: "180ms",
  slow: "250ms",
} as const;

export const zIndex = {
  backdrop: 40,
  modal: 50,
  drawer: 50,
  popover: 30,
  header: 20,
  sidebar: 20,
  toast: 60,
} as const;

export const breakpoints = {
  smallMobile: 390,
  mobile: 768,
  tablet: 1024,
  laptop: 1280,
  desktop: 1440,
} as const;
