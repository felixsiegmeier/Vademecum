export interface InitialUpload {
  fileName: string;
  summary: string;
  proposals: Array<{
    id: string;
    tool: string;
    args: Record<string, string>;
    source_quote: string;
  }>;
}
