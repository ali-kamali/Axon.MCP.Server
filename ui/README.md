# Axon MCP Server - UI Dashboard

A modern React + TypeScript dashboard for monitoring and managing the Axon MCP Server.

## Features

- 🏥 **Health Monitoring** - Real-time service health, version, and environment information
- 📊 **Metrics Dashboard** - Display Prometheus metrics from the backend
- 📦 **Repository Management** - List and sync GitLab repositories
- 🎨 **Modern UI** - Clean, dark-themed interface with responsive design
- 🔧 **Type-Safe** - Full TypeScript support with strict typing
- ✅ **Tested** - Unit tests with Vitest and React Testing Library

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **React Router** - Client-side routing
- **Axios** - HTTP client
- **CSS Modules** - Scoped styling
- **Vitest** - Unit testing
- **ESLint + Prettier** - Code quality

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Axon MCP Server running (default: `http://localhost:8080`)

### Installation

```bash
# Install dependencies
npm install
```

### Configuration

Create a `.env` file (or copy from `.env.example`):

```bash
# API Configuration
VITE_API_BASE_URL=http://localhost:8080
```

### Development

```bash
# Start dev server (http://localhost:5173)
npm run dev

# Run tests
npm test

# Run tests in watch mode
npm test -- --watch

# Lint code
npm run lint

# Type check
npm run typecheck
```

### Production Build

```bash
# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
ui/
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── health_card/     # Service health display
│   │   ├── metrics_panel/   # Metrics visualization
│   │   └── repo_table/      # Repository table
│   ├── pages/               # Page components
│   │   ├── dashboard/       # Main dashboard
│   │   ├── repositories/    # Repository management
│   │   └── settings/        # Settings page
│   ├── services/            # API service layer
│   │   └── api.ts          # HTTP client and API methods
│   ├── styles/              # Global styles
│   │   ├── globals.css     # Global CSS
│   │   └── tokens.css      # Design tokens
│   ├── test/                # Test utilities
│   │   └── setup.ts        # Test setup
│   ├── types/               # TypeScript types
│   │   └── enums.ts        # Enums (no raw strings)
│   ├── App.tsx             # Root component
│   └── main.tsx            # Entry point
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── vitest.config.ts
└── README.md
```

## Code Conventions

### Naming Conventions

- **CSS Classes**: `snake_case` (e.g., `.health_container`, `.nav_link_active`)
- **Components**: `PascalCase` (e.g., `HealthCard`, `MetricsPanel`)
- **Files**: Match component names (e.g., `HealthCard.tsx`, `HealthCard.module.css`)
- **Enums**: `PascalCase` with Enum suffix (e.g., `EnvironmentEnum`, `RepositoryStatusEnum`)

### Styling

- ✅ Use CSS Modules for component styles
- ✅ Use design tokens from `tokens.css`
- ✅ Follow `snake_case` for class names
- ❌ No inline styles
- ❌ No raw string constants (use enums)

### Example Component

```tsx
import styles from "./MyComponent.module.css";
import { EnvironmentEnum } from "../../types/enums";

type MyComponentProps = {
  environment: EnvironmentEnum;
};

export default function MyComponent({ environment }: MyComponentProps) {
  return (
    <div className={styles.my_component_container}>
      <span className={styles.environment_badge}>
        {environment}
      </span>
    </div>
  );
}
```

## API Integration

The UI communicates with the Axon MCP Server REST API:

### Available Endpoints

- `GET /api/v1/health` - Service health information
- `GET /api/v1/metrics` - Prometheus metrics (text format)
- `GET /api/v1/repositories` - List repositories (when available)
- `POST /api/v1/repositories/sync` - Sync repository (when available)

### API Service Layer

All API calls go through `src/services/api.ts`:

```typescript
import { getHealth, getMetricsRaw } from "./services/api";

// Fetch health data
const health = await getHealth();

// Fetch metrics
const metrics = await getMetricsRaw();
```

## Testing

### Running Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run tests with coverage
npm test -- --coverage
```

### Writing Tests

Tests are located next to their components:

```
src/components/health_card/
├── HealthCard.tsx
├── HealthCard.module.css
└── HealthCard.test.tsx
```

Example test:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import HealthCard from "./HealthCard";

describe("HealthCard", () => {
  it("renders service name", () => {
    render(
      <HealthCard
        status="healthy"
        service="Axon MCP Server"
        version="1.0.0"
        environment="development"
      />
    );

    expect(screen.getByText("Axon MCP Server")).toBeInTheDocument();
  });
});
```

## CORS Configuration

If running the UI and API on different ports, ensure CORS is configured in the backend:

```python
# In backend settings
api_cors_origins = ["http://localhost:5173"]
```

## Deployment

### Docker Compose (Recommended)

The UI is now integrated into the main Docker Compose setup! From the project root:

```bash
# Start all services including UI
docker-compose -f docker/docker-compose.yml up -d

# The UI will be available at http://localhost:80
```

See [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed deployment instructions.

### Available After Deployment

- **React Dashboard**: http://localhost:80
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **API Swagger**: http://localhost:8080/api/docs

### Static Hosting

Build and deploy the `dist/` folder to any static hosting service:

```bash
npm run build
# Deploy the dist/ folder
```

## Troubleshooting

### API Connection Issues

1. Check that the backend is running: `curl http://localhost:8080/api/v1/health`
2. Verify `VITE_API_BASE_URL` in `.env`
3. Check browser console for CORS errors
4. Ensure backend CORS settings allow the UI origin

### Build Errors

1. Clear node_modules: `rm -rf node_modules && npm install`
2. Clear build cache: `rm -rf dist .vite`
3. Check Node.js version: `node --version` (should be 18+)

## Contributing

1. Follow the naming conventions (snake_case for CSS, enums for constants)
2. Write tests for new components
3. Run linter before committing: `npm run lint`
4. Ensure type safety: `npm run typecheck`

## License

Part of the Axon MCP Server project.

