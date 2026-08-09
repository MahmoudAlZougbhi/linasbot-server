import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { asRecord, asRecordList, emptyLabels, newId, primaryLabel } from '../cmApi';
import { cmFormStyles } from '../cmFormStyles';
import { Field } from './Field';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
};

type DimPair = { key: string; value: string };

/**
 * Simple price-list catalog builder over real PricesSection fields:
 * price_books (list title) + dimension_definitions (reusable columns) +
 * catalog (list root item) + price_entries (rows with dimensions + amount).
 */
export function PricesEditor({ payload, onChange }: Props) {
  const books = asRecordList(payload.price_books);
  const catalog = asRecordList(payload.catalog);
  const entries = asRecordList(payload.price_entries);
  const dimensions = asRecordList(payload.dimension_definitions);

  const [bookId, setBookId] = useState<string | null>(books[0] ? String(books[0].id) : null);
  const selectedBook = books.find((b) => String(b.id) === bookId) || books[0] || null;

  const bookEntryIds = useMemo(() => {
    if (!selectedBook) return new Set<string>();
    const ids = Array.isArray(selectedBook.entry_ids) ? selectedBook.entry_ids.map(String) : [];
    return new Set(ids);
  }, [selectedBook]);

  const bookEntries = entries.filter((e) => bookEntryIds.has(String(e.id)));

  const [rowId, setRowId] = useState<string | null>(null);
  const selectedRow =
    bookEntries.find((e) => String(e.id) === rowId) || bookEntries[0] || null;

  const [draftDims, setDraftDims] = useState<DimPair[]>([{ key: '', value: '' }]);
  const [draftPrice, setDraftPrice] = useState('0');
  const [draftCurrency, setDraftCurrency] = useState('USD');

  const patchPayload = (patch: Record<string, unknown>) => onChange({ ...payload, ...patch });

  const ensureDimension = (
    defs: Record<string, unknown>[],
    key: string,
    value: string,
  ): Record<string, unknown>[] => {
    const id = key
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_|_$/g, '');
    if (!id) return defs;
    const existing = defs.find((d) => String(d.id) === id);
    if (!existing) {
      return [
        ...defs,
        {
          id,
          labels: { ...emptyLabels(), en: key.trim() },
          value_type: 'string',
          allowed_values: value.trim() ? [value.trim()] : [],
          required: false,
          active: true,
          notes: null,
        },
      ];
    }
    const allowed = Array.isArray(existing.allowed_values)
      ? existing.allowed_values.map(String)
      : [];
    const nextAllowed =
      value.trim() && !allowed.includes(value.trim()) ? [...allowed, value.trim()] : allowed;
    return defs.map((d) =>
      String(d.id) === id ? { ...d, allowed_values: nextAllowed, active: true } : d,
    );
  };

  const addBook = () => {
    const id = newId('book');
    const catalogId = newId('catalog');
    patchPayload({
      price_books: [
        {
          id,
          labels: { ...emptyLabels(), en: '' },
          currency: 'USD',
          entry_ids: [],
          branch_ids: [],
          audience: 'any',
          active: true,
          effective: {},
          provenance: 'mobile_simple',
          revision: 1,
          notes: null,
        },
        ...books,
      ],
      catalog: [
        {
          id: catalogId,
          item_type: 'custom',
          category_ids: [],
          labels: { ...emptyLabels(), en: `Price list ${id}` },
          aliases: [],
          description: '',
          base_price: null,
          currency: 'USD',
          variants: [],
          branch_ids: [],
          audience: 'any',
          unit: null,
          discount_eligible: true,
          active: true,
          effective: {},
          provenance: 'mobile_simple',
          revision: 1,
          notes: id,
        },
        ...catalog,
      ],
    });
    setBookId(id);
  };

  const patchBook = (id: string, data: Record<string, unknown>) => {
    patchPayload({
      price_books: books.map((b) => (String(b.id) === id ? { ...b, ...data } : b)),
    });
  };

  const catalogForBook = (book: Record<string, unknown>) => {
    const byNotes = catalog.find((c) => String(c.notes || '') === String(book.id));
    if (byNotes) return byNotes;
    return (
      catalog.find((c) => primaryLabel(c.labels) === primaryLabel(book.labels)) || catalog[0] || null
    );
  };

  const addRow = () => {
    if (!selectedBook) return;
    const pairs = draftDims.filter((d) => d.key.trim() && d.value.trim());
    const amount = Number(draftPrice);
    if (!Number.isFinite(amount) || amount < 0) return;

    let nextDims = dimensions;
    const dimMap: Record<string, string> = {};
    for (const pair of pairs) {
      nextDims = ensureDimension(nextDims, pair.key, pair.value);
      const dimId = pair.key
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_|_$/g, '');
      dimMap[dimId] = pair.value.trim();
    }

    const cat = catalogForBook(selectedBook);
    const catalogItemId = cat ? String(cat.id) : newId('catalog');
    let nextCatalog = catalog;
    if (!cat) {
      nextCatalog = [
        {
          id: catalogItemId,
          item_type: 'custom',
          category_ids: [],
          labels: {
            ...emptyLabels(),
            en: primaryLabel(selectedBook.labels) || String(selectedBook.id),
          },
          aliases: [],
          description: '',
          base_price: null,
          currency: draftCurrency || 'USD',
          variants: [],
          branch_ids: [],
          audience: 'any',
          unit: null,
          discount_eligible: true,
          active: true,
          effective: {},
          provenance: 'mobile_simple',
          revision: 1,
          notes: String(selectedBook.id),
        },
        ...catalog,
      ];
    }

    const entryId = newId('entry');
    const nextEntries = [
      {
        id: entryId,
        catalog_item_id: catalogItemId,
        variant_id: null,
        amount,
        currency: draftCurrency || 'USD',
        branch_id: null,
        audience: 'any',
        unit: null,
        min_quantity: null,
        max_quantity: null,
        duration_minutes: null,
        size: null,
        dimensions: dimMap,
        active: true,
        effective: {},
        provenance: 'mobile_simple',
        revision: 1,
        notes: null,
      },
      ...entries,
    ];

    const entryIds = Array.isArray(selectedBook.entry_ids)
      ? selectedBook.entry_ids.map(String)
      : [];
    patchPayload({
      dimension_definitions: nextDims,
      catalog: nextCatalog,
      price_entries: nextEntries,
      price_books: books.map((b) =>
        String(b.id) === String(selectedBook.id)
          ? { ...b, entry_ids: [entryId, ...entryIds], currency: draftCurrency || 'USD' }
          : b,
      ),
    });
    setRowId(entryId);
    setDraftDims([{ key: '', value: '' }]);
    setDraftPrice('0');
  };

  const knownDimNames = dimensions.map((d) => primaryLabel(d.labels) || String(d.id));

  return (
    <View>
      <Text style={cmFormStyles.hint}>
        Build price lists like a catalog book. Titles and attribute values stay saved for reuse.
      </Text>
      <PrimaryButton label="Add price list" onPress={addBook} variant="ghost" />
      <View style={{ height: 12 }} />
      {books.map((book) => (
        <Pressable
          key={String(book.id)}
          style={[
            cmFormStyles.itemCard,
            selectedBook && String(selectedBook.id) === String(book.id)
              ? { borderColor: '#2563EB' }
              : null,
          ]}
          onPress={() => setBookId(String(book.id))}
        >
          <Text style={cmFormStyles.itemTitle}>
            {primaryLabel(book.labels) || String(book.id)}
          </Text>
          <Text style={cmFormStyles.itemSub}>
            {Array.isArray(book.entry_ids) ? book.entry_ids.length : 0} rows
          </Text>
        </Pressable>
      ))}

      {selectedBook ? (
        <View style={cmFormStyles.card}>
          <Field
            label="Price list title"
            value={String(asRecord(selectedBook.labels).en || '')}
            onChange={(v) =>
              patchBook(String(selectedBook.id), {
                labels: { ...emptyLabels(), ...asRecord(selectedBook.labels), en: v },
              })
            }
            placeholder="e.g. Laser hair removal price list"
          />

          <Text style={[cmFormStyles.label, { marginTop: 8 }]}>Rows</Text>
          {bookEntries.map((entry) => {
            const dims = asRecord(entry.dimensions);
            const dimText = Object.entries(dims)
              .map(([k, v]) => `${k}: ${String(v)}`)
              .join(' · ');
            return (
              <Pressable
                key={String(entry.id)}
                style={cmFormStyles.itemCard}
                onPress={() => setRowId(String(entry.id))}
              >
                <Text style={cmFormStyles.itemTitle}>
                  {String(entry.amount ?? 0)} {String(entry.currency || 'USD')}
                </Text>
                <Text style={cmFormStyles.itemSub}>{dimText || 'No attributes'}</Text>
              </Pressable>
            );
          })}

          <Text style={[cmFormStyles.label, { marginTop: 8 }]}>Add row</Text>
          {knownDimNames.length > 0 ? (
            <Text style={cmFormStyles.hint}>Saved attributes: {knownDimNames.join(', ')}</Text>
          ) : null}
          {draftDims.map((pair, index) => (
            <View key={`dim-${index}`} style={{ marginBottom: 8 }}>
              <Field
                label="Attribute name"
                value={pair.key}
                onChange={(v) => {
                  const next = [...draftDims];
                  next[index] = { ...pair, key: v };
                  setDraftDims(next);
                }}
                placeholder="Machine / Body part / Branch"
              />
              <Field
                label="Value"
                value={pair.value}
                onChange={(v) => {
                  const next = [...draftDims];
                  next[index] = { ...pair, value: v };
                  setDraftDims(next);
                }}
                placeholder="Trio / Arms / Beirut"
              />
            </View>
          ))}
          <PrimaryButton
            label="Add attribute column"
            variant="ghost"
            onPress={() => setDraftDims([...draftDims, { key: '', value: '' }])}
          />
          <Field label="Price" value={draftPrice} onChange={setDraftPrice} placeholder="70" />
          <Field label="Currency" value={draftCurrency} onChange={setDraftCurrency} />
          <PrimaryButton label="Save row" onPress={addRow} />
          {selectedRow ? (
            <Text style={[cmFormStyles.hint, { marginTop: 8 }]}>
              Selected row: {String(selectedRow.id)}
            </Text>
          ) : null}
        </View>
      ) : (
        <Text style={cmFormStyles.hint}>No price lists yet — tap Add price list.</Text>
      )}
    </View>
  );
}
