<template>
  <div style="height: 100vh; min-height: 1200px; display: flex; flex-direction: column;">
    <div ref="tablesWrapper"
      style="position: fixed; top: 0; width: 100vw; z-index: 100; background-color: white; margin:0px; padding: 0px;">
      <span class="fold-icon" @click="isTablesWrapperFolded = !isTablesWrapperFolded" style="cursor: pointer;">
        <template v-if="!isTablesWrapperFolded">
          <svg width="20px" height="20px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 12L18 12" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </template>
        <template v-else>
          <svg width="20px" height="20px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M4 12H20M12 4V20" stroke="#000000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </template>
      </span>
      <table class="table table-borderless small-text m-0 table-border-bottom">
        <thead>
          <tr>
            <th scope="col" class="p-1" v-show="transferInActivities.includes(activity)">Expected</th>
            <th scope="col" class="p-1">Done</th>
            <th scope="col" class="p-1" v-show="transferInActivities.includes(activity)">Pending</th>
            <th scope="col" class="p-1">Weight</th>
            <th scope="col" class="p-1">Actual Loss</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="p-1" v-show="transferInActivities.includes(activity)">{{ crate_summary.expected }}
            </td>
            <td class="p-1">{{ crate_summary.done }}</td>
            <td class="p-1" v-show="transferInActivities.includes(activity)">{{ crate_summary.pending }}
            </td>
            <td class="p-1">{{ crate_summary.weight }}KG</td>
            <td class="p-1">{{ crate_summary.actual_loss }}KG</td>
          </tr>
        </tbody>
      </table>

      <table class="table table-borderless small-text m-0" v-if="!isTablesWrapperFolded">
        <thead>
          <tr>
            <th class="p-1 fixed-width-sku" scope="col">SKU</th>
            <th class="p-1 fixed-width-count" scope="col">Count</th>
            <th class="p-1 fixed-width-grn" scope="col">GRN Qty</th>
            <th class="p-1 fixed-width-grn" scope="col">Weight</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in item_summary">
            <td class="p-1 fixed-width-sku" v-if="row.item_code">{{ row.item_name }}({{ row.item_code }})</td>
            <td class="p-1 fixed-width-sku" v-else>Empty Crate</td>
            <td class="p-1 fixed-width-count">{{ row.count }}</td>
            <td class="p-1 fixed-width-grn" v-if="transferInActivities.includes(activity)">
              {{ row.quantity }}/{{ row.expected_quantity }}
              {{ row.stock_uom === 'KG' ? 'KG' : (row.stock_uom === 'Nos' ? 'Pcs' : '') }}
            </td>
            <td class="p-1 fixed-width-grn" v-else>
              {{ row.quantity }}
              {{ row.stock_uom === 'KG' ? 'KG' : (row.stock_uom === 'Nos' ? 'Pcs' : '') }}
            </td>
            <td class="p-1 fixed-width-grn" scope="col" v-if="transferInActivities.includes(activity)">{{ row.weight }}/{{ row.expected_weight }}KG</td>
            <td class="p-1 fixed-width-grn" scope="col" v-else>{{ row.weight }}KG</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div ref="scrollableContent" style="flex-grow: 1; overflow: auto; margin:0px; padding:0px;">
      <ul class="list-group scroller">
        <div class="card m-0"
          v-for="(item, index) in Object.values(crates).filter(c => c && c.modified).sort((a, b) => new Date(b.modified) - new Date(a.modified))">
          <div class="card-body small-text" v-if="item" :key="item.crate_id">
            <div class="d-flex justify-content-between align-items-baseline">
              <h4 class="mb-0 flex-grow-1 mr-0 mt-0">{{ item.crate_id }}</h4>
              <span v-if="item.stock_uom">{{ item.grn_quantity }}</span><span v-if="item.stock_uom === 'KG'">&nbsp;
                KG</span><span v-if="item.stock_uom === 'Nos'">&nbsp;Pcs</span>
            </div>
            <div class="d-flex justify-content-between align-items-center">
              <p class="mb-0" v-if="item.item_name && item.supplier_name">
                {{ item.item_name }} procured at {{ item.procurement_warehouse_name }} from {{ item.supplier_name }} on
                {{
                  item.procurement_timestamp ? item.procurement_timestamp.split('.')[0] : ''
                }}
              </p>
              <div style="display: flex; justify-content: flex-end;">
                <button @click="editQuantity(item.crate_id, item.grn_quantity)" class="btn icon-btn mr-2 p-2" title="Edit"
                  v-if="activity === 'Procurement' && item.stock_uom === 'Nos' && item.status === 'Draft' && index === 0">
                  <svg width="20px" height="20px" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path fill-rule="evenodd" clip-rule="evenodd"
                      d="M20.8477 1.87868C19.6761 0.707109 17.7766 0.707105 16.605 1.87868L2.44744 16.0363C2.02864 16.4551 1.74317 16.9885 1.62702 17.5692L1.03995 20.5046C0.760062 21.904 1.9939 23.1379 3.39334 22.858L6.32868 22.2709C6.90945 22.1548 7.44285 21.8693 7.86165 21.4505L22.0192 7.29289C23.1908 6.12132 23.1908 4.22183 22.0192 3.05025L20.8477 1.87868ZM18.0192 3.29289C18.4098 2.90237 19.0429 2.90237 19.4335 3.29289L20.605 4.46447C20.9956 4.85499 20.9956 5.48815 20.605 5.87868L17.9334 8.55027L15.3477 5.96448L18.0192 3.29289ZM13.9334 7.3787L3.86165 17.4505C3.72205 17.5901 3.6269 17.7679 3.58818 17.9615L3.00111 20.8968L5.93645 20.3097C6.13004 20.271 6.30784 20.1759 6.44744 20.0363L16.5192 9.96448L13.9334 7.3787Z"
                      fill="#0F0F0F" />
                  </svg>
                </button>
                <button @click="deleteCrate(item.crate_id)" class="btn icon-btn p-2" title="Delete"
                  v-if="item.status === 'Draft' && allowDelete.includes(activity)">
                  <svg width="20px" height="20px" viewBox="0 -0.5 21 21" version="1.1" xmlns="http://www.w3.org/2000/svg"
                    xmlns:xlink="http://www.w3.org/1999/xlink">

                    <title>delete [#1487]</title>
                    <desc>Created with Sketch.</desc>
                    <defs>

                    </defs>
                    <g id="Page-1" stroke="none" stroke-width="1" fill="none" fill-rule="evenodd">
                      <g id="Dribbble-Light-Preview" transform="translate(-179.000000, -360.000000)" fill="#000000">
                        <g id="icons" transform="translate(56.000000, 160.000000)">
                          <path
                            d="M130.35,216 L132.45,216 L132.45,208 L130.35,208 L130.35,216 Z M134.55,216 L136.65,216 L136.65,208 L134.55,208 L134.55,216 Z M128.25,218 L138.75,218 L138.75,206 L128.25,206 L128.25,218 Z M130.35,204 L136.65,204 L136.65,202 L130.35,202 L130.35,204 Z M138.75,204 L138.75,200 L128.25,200 L128.25,204 L123,204 L123,206 L126.15,206 L126.15,220 L140.85,220 L140.85,206 L144,206 L144,204 L138.75,204 Z"
                            id="delete-[#1487]">

                          </path>
                        </g>
                      </g>
                    </g>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </ul>
    </div>
  </div>
</template>



<script>
export default {
  name: "ActivitySummary",
  props: {
    session_id: String,
    activity: String,
    crate_summary: Object,
    item_summary: Array,
    crates: Object,
    items: Array,
  },
  data() {
    return {
      tableHeight: 0,
      allowDelete: ['Procurement', 'Transfer Out', 'Bulk Transfer In', 'Crate Tracking Out', 'Material Request'],
      transferInActivities: ["Transfer In", "Bulk Transfer In", "Crate Tracking In"],
      sortedCrates: [],
      isTablesWrapperFolded: false, // True if tablesWrapper is folded, false otherwise
    };
  },
  methods: {
    refresh() {
      this.$emit('refresh');
    },
    deleteCrate(crate_id) {
      const crate = {
        crate_id,
        current_activity: this.activity
      }
      const activity = "Delete";
      const message = `Are you sure you want to delete crate ${crate_id} from this document?`;

      if (window.confirm(message)) {
        frappe.call({
          method: "iotready_godesi.utils.delete_crate",
          type: "POST",
          args: {
            crate,
            activity
          },
          callback: (r) => {
            console.log(r);
            if (r.exc) {
              console.error(r.exc);
              // frappe.throw("Something went wrong. Please try again.");
              window.alert("Something went wrong. Please try again.");
            } else {
              this.$emit('delete-crate', crate_id);
              this.$emit('refresh');
              AndroidBridge.deleteCrate(crate_id);
            }
          },
          freeze: true,
          freeze_message: "Please wait...",
          async: true,
        });
      }
    },
    editQuantity(crate_id, quantity) {
      AndroidBridge.editProcuredQuantity(crate_id, 1, quantity)
    },
    // updateSortedCrates() {
    //   console.log("sorting crates")
    //   this.sortedCrates = Object.values(this.crates).sort((a, b) => new Date(b.modified) - new Date(a.modified));
    // }
  },
  watch: {
    tableHeight(newValue) {
      // set the padding-top of the scrollable content here
      this.$refs.scrollableContent.style.paddingTop = newValue + 'px';
    },
    // crates: {
    //   handler() {
    //     this.updateSortedCrates();
    //   },
    //   deep: true,
    // }
  },
  mounted() {
    // watch for changes in the height of the tables wrapper
    if (this.$refs && this.$refs.tablesWrapper) {
      this.tableHeight = this.$refs.tablesWrapper.clientHeight;

      const observer = new ResizeObserver(entries => {
        for (let entry of entries) {
          this.tableHeight = entry.contentRect.height;
        }
      });
      observer.observe(this.$refs.tablesWrapper);
    }
  }
}
</script>


<style>
.small-text {
  font-size: 0.75rem !important;
}

.icon-btn {
  font-size: 1.5em;
  /* display: inline-block; */
  padding: 0.5em;
}

.table-border-bottom {
  border-bottom: 1px solid #dee2e6;
}

.card {
  margin: 0 !important;
  padding: 0 !important;
  border-radius: 0;
}

.card-body {
  margin: 0 !important;
  padding-left: 5px !important;
  padding-right: 5px !important;
  padding-top: 5px !important;
  padding-bottom: 0px !important;
}

.refresh-button {
  position: absolute;
  top: 55px;
  right: 5px;
  /* moved it a bit to the left */
}

.fold-icon {
  font-size: 1.2em;
  position: absolute;
  right: 5px;
  top: 5px;
}

.fixed-width-sku {
  max-width: 4ch;
  /* 4 columns */
  white-space: normal;
  /* Allows text to wrap */
  word-wrap: break-word;
  /* Wraps onto next line */
}

.fixed-width-count {
  max-width: 2ch;
  /* 2 columns */
  white-space: nowrap;
  /* Prevents text from wrapping */
}
.fixed-width-grn {
  max-width: 3ch;
  /* 3 columns */
  white-space: normal;
  /* Allows text to wrap */
  word-wrap: break-word;
  /* Wraps onto next line */
}
</style>
