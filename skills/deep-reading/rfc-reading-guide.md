# RFC Reading Guide

Specific guidelines for reading IETF RFCs effectively. Apply these on top of the general reading flow.

## Document Identity Check

Before reading content, clarify:
- **Stream**: IETF stream = community consensus; independent/IAB/IRTF streams have different authority levels
- **Category**: Standards Track vs Informational vs Experimental vs BCP — only Standards Track defines normative protocol behavior
- **Currency**: Check Obsoletes/Updates relationships; point user to the most current document. Note any errata that affect interpretation.
- **Internet-Draft vs RFC**: If it's a draft, warn that it's a proposal, not a standard

## Requirement Keywords (RFC 2119/8174)

Help users correctly interpret MUST/SHOULD/MAY:
- **MUST**: Absolute requirement — violating this breaks interoperability
- **SHOULD**: Strong recommendation with known exceptions — explain WHAT the exceptions are when the spec states them
- **SHOULD does NOT mean optional** — it means "do this unless you have a specific, documented reason not to"
- **Target matters**: Identify WHO the requirement applies to (sender vs receiver, client vs server, proxy vs endpoint). A "MUST NOT send" does not automatically mean "MUST reject on receive"
- **Implicit permissions**: What is not explicitly disallowed is generally allowed. Warn users against reading too much into specs.

## Context and Cross-References

- Never interpret a statement in isolation — always check referenced sections and related specs
- IANA registries (not the RFC itself) are the source of truth for extension points (methods, headers, status codes, etc.)
- When a section references another RFC, briefly explain what it says rather than just noting the reference

## Examples and ABNF

- **Examples are not normative** — they often lag behind spec changes and may be truncated or simplified. Always verify against the actual requirement text.
- **ABNF is aspirational** — it defines what to generate, not necessarily what to accept. Parsing often needs to be more lenient than ABNF implies.
- When explaining ABNF, translate it into plain language and highlight where real-world implementations commonly deviate.

## Security Considerations

- Always flag the Security Considerations section as worth reading
- Summarize key security implications proactively, even if the user doesn't ask
- Follow security references to give the user a complete threat picture

## Common Pitfalls When Reading RFCs

| Pitfall | Correct approach |
|---------|-----------------|
| Implementing from examples only | Examples are illustrative, not normative — read the requirement text |
| Rejecting messages that violate a sender MUST | Sender requirements don't imply receiver behavior unless stated |
| Treating SHOULD as optional | SHOULD means "do it unless you have a documented reason not to" |
| Reading one section in isolation | Always follow cross-references; context changes meaning |
| Assuming the RFC is the complete truth | Check IANA registries for extension points; check errata for corrections |
| Enforcing ABNF strictly on input | ABNF defines ideal output; input parsing often needs to be lenient |
