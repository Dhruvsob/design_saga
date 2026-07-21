import { CaretRight } from "@phosphor-icons/react";

/**
 * Consistent page hero used across all top-level pages.
 * Renders eyebrow, big editorial title, kicker, and action buttons.
 */
export default function PageHero({
  eyebrow,
  title,
  kicker,
  children,        // action buttons / right-side content
  count,           // optional badge count
  testid,
}) {
  return (
    <div
      className="fade-up flex items-start justify-between flex-wrap gap-4 pb-6 border-b border-[#E5E5E5]"
      data-testid={testid}
    >
      <div className="min-w-0">
        <div className="overline mb-3 flex items-center gap-3">
          {eyebrow}
          {typeof count === "number" && (
            <>
              <CaretRight size={9} className="text-[#9A9A9A]" />
              <span className="font-mono">{count} ITEMS</span>
            </>
          )}
        </div>
        <h1 className="font-display font-bold tracking-tighter text-4xl lg:text-5xl leading-[0.95]">
          {title}
        </h1>
        {kicker && <p className="text-[#5C5C5C] mt-2 max-w-xl">{kicker}</p>}
      </div>
      <div className="flex items-center gap-3 flex-shrink-0">{children}</div>
    </div>
  );
}
