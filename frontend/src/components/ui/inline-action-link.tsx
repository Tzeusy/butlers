import * as React from "react"

import { cn } from "@/lib/utils"

type InlineActionButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  as?: "button"
}

type InlineActionAnchorProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & {
  as: "a"
}

type InlineActionSummaryProps = React.HTMLAttributes<HTMLElement> & {
  as: "summary"
}

export type InlineActionLinkProps =
  | InlineActionButtonProps
  | InlineActionAnchorProps
  | InlineActionSummaryProps

const baseClassName = [
  "inline-flex min-h-11 min-w-11 items-center justify-center",
  "font-mono text-[11px] uppercase tracking-wider",
  "text-muted-foreground underline underline-offset-2",
  "transition-colors hover:text-foreground cursor-pointer",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
  "disabled:cursor-default disabled:opacity-50",
].join(" ")

/**
 * Canonical compact text action. It keeps the established mono-uppercase
 * affordance while giving every consumer a real focus treatment, a 44px
 * target, and native disabled semantics for buttons.
 */
export function InlineActionLink(props: InlineActionLinkProps) {
  if (props.as === "a") {
    const { as: _as, className, ...anchorProps } = props

    return <a data-slot="inline-action-link" className={cn(baseClassName, className)} {...anchorProps} />
  }

  if (props.as === "summary") {
    const { as: _as, className, ...summaryProps } = props

    return (
      <summary
        data-slot="inline-action-link"
        className={cn(baseClassName, "list-none", className)}
        {...summaryProps}
      />
    )
  }

  const { as: _as, className, type, ...buttonProps } = props

  return (
    <button
      data-slot="inline-action-link"
      type={type ?? "button"}
      className={cn(baseClassName, className)}
      {...buttonProps}
    />
  )
}
