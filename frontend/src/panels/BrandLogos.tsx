/**
 * Provider marks for "Connect with …" buttons. Mistral AI mark from Simple Icons (CC0);
 * Microsoft four-square mark as published for "Sign in with Microsoft" buttons.
 */
export function MistralLogo({ size = 18 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden
      role="img"
      style={{ flex: 'none' }}
    >
      <path
        fill="#FA520F"
        d="M17.143 3.429v3.428h-3.429v3.429h-3.428V6.857H6.857V3.43H3.43v13.714H0v3.428h10.286v-3.428H6.857v-3.429h3.429v3.429h3.429v-3.429h3.428v3.429h-3.428v3.428H24v-3.428h-3.43V3.429z"
      />
    </svg>
  );
}

export function MicrosoftLogo({ size = 18 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 21 21"
      width={size}
      height={size}
      aria-hidden
      role="img"
      style={{ flex: 'none' }}
    >
      <rect x="1" y="1" width="9" height="9" fill="#F25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7FBA00" />
      <rect x="1" y="11" width="9" height="9" fill="#00A4EF" />
      <rect x="11" y="11" width="9" height="9" fill="#FFB900" />
    </svg>
  );
}
