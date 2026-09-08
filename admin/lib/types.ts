// Mirrors src/schemas/admin.py and src/schemas/api.py on the backend.

export interface TenantSummary {
  tenant_id: string;
  name: string;
  plan: string;
  created_at: string;
  active_key_count: number;
}

export interface TenantCreateResponse {
  tenant_id: string;
  name: string;
  api_key: string;
  key_prefix: string;
}

export interface KeySummary {
  key_prefix: string;
  created_at: string;
  revoked_at: string | null;
}

export interface MintKeyResponse {
  api_key: string;
  key_prefix: string;
}

export interface CatalogUpsertResponse {
  upserted: number;
}

export interface SimulateReviewResponse {
  simulated_rating: number;
  simulated_review: string;
  confidence: number;
  decision_factors: string[];
}

export interface RecommendedItem {
  rank: number;
  item_id: string;
  name: string;
  category: string;
  predicted_rating: number;
  explanation: string;
  ndcg_score: number | null;
}

export interface RecommendResponse {
  recommendations: RecommendedItem[];
  inferred_intent: string;
  cold_start: boolean;
  decision_factors: string[];
}
