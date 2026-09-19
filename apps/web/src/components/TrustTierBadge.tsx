type Tier = { label: string; tone: string; help: string };

const TIERS: Record<string, Tier> = {
  human_verified: {
    label: "Human verified",
    tone: "ok",
    help: "A person confirmed this content (verified by human:…).",
  },
  agent_verified: {
    label: "Agent verified",
    tone: "info",
    help: "Only an agent has checked this content; no person has confirmed it.",
  },
  generated: {
    label: "Unverified",
    tone: "warn",
    help: "Generated content that nobody has verified yet.",
  },
};

const UNKNOWN: Tier = {
  label: "No provenance",
  tone: "muted",
  help: "The document does not say who wrote or checked it.",
};

export function trustTier(tier: string): Tier {
  return TIERS[tier] ?? UNKNOWN;
}

export function TrustTierBadge({ tier }: { tier: string }) {
  const info = trustTier(tier);
  return (
    <span className={`badge badge--${info.tone}`} title={info.help}>
      {info.label}
    </span>
  );
}
