import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { api, type Credentials, type RegisterInput } from "@/lib/api";

export function AuthProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function useAuth() {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["auth", "me"], queryFn: api.me });
  const saveUser = (user: Awaited<ReturnType<typeof api.me>>) => queryClient.setQueryData(["auth", "me"], user);
  return {
    user: me.data ?? null,
    isLoading: me.isPending,
    login: useMutation({ mutationFn: (input: Credentials) => api.login(input), onSuccess: saveUser }),
    register: useMutation({ mutationFn: (input: RegisterInput) => api.register(input), onSuccess: saveUser }),
    logout: useMutation({ mutationFn: api.logout, onSuccess: () => queryClient.setQueryData(["auth", "me"], null) }),
  };
}
