<script lang="ts">
  import { Accordion } from 'bits-ui'
  import Plus from 'phosphor-svelte/lib/Plus'

  export interface FaqEntry {
    readonly id: string
    readonly tag?: string
    readonly question: string
    readonly answer: string
  }

  interface Props {
    items: readonly FaqEntry[]
  }

  let { items }: Props = $props()
</script>

<Accordion.Root
  type="multiple"
  value={items[0] ? [items[0].id] : []}
  class="flex flex-col gap-3.5"
>
  {#each items as item, idx (item.id)}
    <Accordion.Item
      value={item.id}
      class="group/item overflow-hidden rounded-2xl border border-[#d7d9df] bg-white transition-colors duration-200 data-[state=open]:border-[#3156d3]/65 data-[state=open]:shadow-[0_14px_34px_-18px_rgba(23,43,77,0.22)]"
    >
      <Accordion.Header>
        <Accordion.Trigger
          class="group flex w-full cursor-pointer items-start justify-between gap-4 px-5 py-5 text-left sm:px-6"
        >
          <div class="flex min-w-0 items-start gap-4">
            <span
              class="mt-0.5 shrink-0 rounded-md border border-[#d7d9df] bg-[#f5f3ec] px-2 py-0.5 font-mono text-[11px] font-medium text-[#3156d3] tabular-nums transition-colors group-data-[state=open]:border-[#3156d3] group-data-[state=open]:bg-[#3156d3] group-data-[state=open]:text-white"
            >
              {String(idx + 1).padStart(2, '0')}
            </span>

            <div class="min-w-0 flex-1">
              {#if item.tag}
                <span
                  class="mb-1 block font-mono text-[10px] tracking-[0.08em] text-[#52617b]"
                >
                  {item.tag}
                </span>
              {/if}
              <span
                class="title-3 block text-[#172b4d] transition-colors group-hover:text-[#3156d3]"
              >
                {item.question}
              </span>
            </div>
          </div>

          <span
            class="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full border border-[#d7d9df] bg-[#f5f3ec] text-[#172b4d] transition-all duration-200 group-hover:border-[#3156d3] group-hover:text-[#3156d3] group-data-[state=open]:rotate-45 group-data-[state=open]:border-[#3156d3] group-data-[state=open]:bg-[#ebefff] group-data-[state=open]:text-[#3156d3]"
            aria-hidden="true"
          >
            <Plus class="size-4" weight="bold" />
          </span>
        </Accordion.Trigger>
      </Accordion.Header>

      <Accordion.Content class="px-5 pb-6 sm:px-6">
        <div
          class="border-t border-[#eae8e1] pt-4 pl-0 sm:pl-12"
        >
          <p class="body-6 leading-relaxed text-[#52617b]">
            {item.answer}
          </p>
        </div>
      </Accordion.Content>
    </Accordion.Item>
  {/each}
</Accordion.Root>
