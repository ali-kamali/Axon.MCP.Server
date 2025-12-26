import { api } from './api';

export interface EnrichmentStats {
    repository_id: number;
    total_symbols: number;
    enriched_count: number;
    coverage_pct: number;
}

export type EnrichmentTriggerResponse = {
    status: string;
    task_id: string;
    repository_id: number;
    message: string;
}

export const enrichmentService = {
    triggerEnrichment: async (repositoryId: number) => {
        const response = await api.post<EnrichmentTriggerResponse>('/api/v1/admin/enrichment/trigger', null, {
            params: { repository_id: repositoryId }
        });
        return response.data;
    },

    getStats: async (repositoryId?: number) => {
        const response = await api.get<EnrichmentStats[]>('/api/v1/admin/enrichment/stats', {
            params: { repository_id: repositoryId }
        });
        return response.data;
    }
};
