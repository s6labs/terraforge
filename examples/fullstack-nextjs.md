---
name: fullstack-nextjs
display_name: Full Stack Next.js
target: docker
language: node
ide: code-server
compute:
  cpu: 4
  memory_gb: 8
  disk_gb: 40
cost:
  auto_stop_hours: 2
---

# Full Stack Next.js Development Workspace

This workspace is optimized for building modern full-stack applications with:

- **Next.js 14** with App Router
- **TypeScript** 5.x
- **Tailwind CSS** + shadcn/ui
- **Prisma** ORM with PostgreSQL
- **tRPC** for type-safe APIs

## Services

The workspace starts with:
- PostgreSQL 16 (via Docker Compose or sidecar)
- Redis for caching/sessions
- Mailhog for local email testing

## Tools Pre-installed

- Node.js 20 LTS
- pnpm (preferred over npm)
- Vercel CLI
- Planetscale CLI
- Git with sensible defaults

## Port Forwarding

- 3000: Next.js dev server
- 5555: Prisma Studio
- 8025: Mailhog UI
