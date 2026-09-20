import { useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../api/client";
import type { StoreOut } from "../../api/types";
import { useChannels } from "../../hooks/useGeometry";
import { errorMessage, useManageMutation } from "../../hooks/useManageData";
import { Field, FormActions, inputCls, Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  store: StoreOut;
}

export const TelegramDialog = ({ open, onClose, store }: Props) => {
  const channels = useChannels();
  const [chatId, setChatId] = useState(store.telegram_chat_id ?? "");
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const keys = [["stores"], ["manage-stores"]];
  const save = useManageMutation(() => api.putTelegram(store.store_id, chatId.trim() || null), keys, chatId.trim() ? "Kanal Telegram disimpan" : "Kanal Telegram dimatikan", onClose);
  const configured = channels.data?.telegram_configured ?? false;
  const dirty = (chatId.trim() || null) !== (store.telegram_chat_id ?? null);
  const test = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      if (dirty) await api.putTelegram(store.store_id, chatId.trim() || null);
      const r = await api.testTelegram(store.store_id);
      setTestResult(r.ok ? "Pesan uji terkirim — cek grup Telegram Anda." : `Gagal: ${r.error}`);
      if (r.ok) toast.success("Pesan uji terkirim");
    } catch (e) {
      setTestResult(errorMessage(e));
    } finally {
      setTesting(false);
    }
  };
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <Modal open={open} onClose={onClose} testId="telegram-dialog" title={`Notifikasi Telegram · ${store.name}`}
      description="Alert toko ini (dibuka & pulih) dikirim ke grup Telegram. Bot token diatur operator di server; di sini cukup chat_id grup.">
      <form onSubmit={submit} className="space-y-4">
        {channels.data && !configured && (
          <p className="rounded-xl border border-warn/40 bg-warn-soft px-3 py-2 text-xs text-txt" data-testid="telegram-not-configured">
            Server belum memiliki <code className="font-mono">TELEGRAM_BOT_TOKEN</code>. chat_id tetap bisa disimpan; pesan mulai terkirim setelah token diisi di <code className="font-mono">.env</code> backend dan server di-restart.
          </p>
        )}
        <Field label="chat_id grup / channel" hint="Angka (grup biasanya diawali -100…) atau @username channel publik. Tambahkan bot ke grup lalu ambil chat_id dari https://api.telegram.org/bot<token>/getUpdates. Kosongkan untuk mematikan.">
          <input value={chatId} onChange={(e) => setChatId(e.target.value)} pattern="-?[0-9]+|@[A-Za-z0-9_]{5,}" maxLength={64} placeholder="-1001234567890" className={`${inputCls} font-mono`} data-testid="telegram-chat-id-input" />
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={test} disabled={!configured || !chatId.trim() || testing} className="ctl h-9 disabled:opacity-50" data-testid="telegram-test-button">
            <Send className="h-4 w-4" aria-hidden="true" /> {testing ? "Mengirim…" : "Kirim pesan uji"}
          </button>
          <span className="text-[11px] text-txt-3" data-testid="telegram-state">
            {store.telegram_chat_id ? `Aktif untuk ${store.telegram_chat_id}` : "Belum aktif untuk toko ini"}
          </span>
        </div>
        {testResult && <p className={`text-xs ${testResult.startsWith("Gagal") || !testResult.startsWith("Pesan") ? "text-danger" : "text-emerald-brand"}`} data-testid="telegram-test-result">{testResult}</p>}
        <FormActions onCancel={onClose} submitLabel="Simpan" pending={save.isPending} testId="telegram-dialog" />
      </form>
    </Modal>
  );
};
