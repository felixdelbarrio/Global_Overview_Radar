export {};

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (options: {
            client_id: string;
            callback: (response: { credential?: string }) => void;
            auto_select?: boolean;
            ux_mode?: "popup" | "redirect";
          }) => void;
          renderButton: (
            container: HTMLElement,
            options: Record<string, unknown>
          ) => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}
