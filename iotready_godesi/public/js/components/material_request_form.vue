<template>
  <div>
    <div class="row row-one no-gutters m-1">
      <div class="form-group col-5" v-show="activity !== 'Crate Splitting'">
        <select v-model="picking_flow" class="form-control" required>
          <option value="">Select Flow</option>
          <option value="by_warehouse">Pick By Warehouse</option>
          <option value="by_item_code">Pick By Item</option>
        </select>
      </div>
      <div class="form-group col-7" v-show="picking_flow === 'by_warehouse'">
        <select v-model="target_warehouse" class="form-control" required>
          <option value="">Select Warehouse</option>
          <option v-for="o in warehouses" :key="o.target_warehouse" :value="o.target_warehouse">
            {{ o.label }}
          </option>
        </select>
      </div>
      <div class="form-group col-7" v-show="picking_flow === 'by_item_code' && activity !== 'Crate Splitting'">
        <select v-model="item_code" class="form-control" required>
          <option value="">Select Item</option>
          <option v-for="o in items" :key="o.item_code" :value="o.item_code">
            {{ o.label }}
          </option>
        </select>
      </div>
      <div class="form-group col" v-show="picking_flow === 'by_item_code' && activity === 'Crate Splitting'">
        <select v-model="item_code" class="form-control" required>
          <option value="">Select Item</option>
          <option v-for="o in items" :key="o.item_code" :value="o.item_code">
            {{ o.label }}
          </option>
        </select>
      </div>
    </div>
    <div class="form-group m-1"
      v-show="picking_flow && ((target_warehouse && warehouses.length > 0) || (item_code && items.length > 0))">
      <select v-model="material_request" class="form-control" required>
        <option value="">Select Material Request</option>
        <option v-for="o in material_requests" :key="`${o.docname}-${o.target_warehouse}-${o.item_code}`" :value="o"
          :disabled="o.picked_quantity >= o.quantity"
          :style="{ 'color': 'red'}">
          {{ o.target_warehouse }} | {{ o.item_name }} (Rack: {{ o.rack_number }}) | {{ o.picked_quantity }} of {{
            o.requested_quantity }} ({{ o.stock_uom }})
        </option>
      </select>
    </div>
    <div class="form-group m-1" v-show="show_manual_option && picking_flow === 'by_item_code' && item_code">
      <div class="d-flex flex-md-row justify-content-between align-items-center w-100">
        <span class="mb-2 mb-md-0">Manual Picking</span>
        <label class="switch">
          <input type="checkbox" v-model="is_manual_picking">
          <span class="slider round"></span>
        </label>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'MaterialRequestForm',
  props: {
    activity: String,
    session_id: String,
    open_material_requests: Array,
    selected_picking_flow: String,
    selected_is_manual_picking: Boolean,
    selected_target_warehouse: String,
    selected_item_code: String,
    selected_material_request: String,
    show_manual_option: Boolean,
    updateMetadata: Function,
  },
  data() {
    return {
      picking_flow: 'by_warehouse',
      warehouses: [],
      items: [],
      material_requests: [],
      target_warehouse: '',
      item_code: '',
      material_request: '',
      dropdown_target_warehouse: null,
      dropdown_item: null,
      filtered_warehouses: [],
      filtered_items: [],
      divHeight: "120px",
      is_manual_picking: false,
      done_mounting: false
    }
  },
  methods: {
    materialRequestItemColor: function (
      quantity,
      picked_quantity
    ) {
      if (picked_quantity >= quantity) {
        return "#222222";
      } else if (picked_quantity > 0) {
        return "#FEDD00";
      } else {
        return "";
      }
    },
    maximizeWebview: function () {
      // this.$refs.selectWrapper.style.height = "240px";
      this.divHeight = "240px";
      this.$nextTick(function () {
        let lists = document.querySelectorAll('.multiselect__content-wrapper');
        lists.forEach(list => {
          list.style.height = '180px';
          list.style.maxHeight = '180px';
        });
      });
    },
    minimizeWebview: function () {
      // this.$refs.selectWrapper.style.height = "120px";
      this.divHeight = "120px";
    },
    update_session_context: function () {
      if (!this.done_mounting) {
        return;
      }
      const metadata = {
        item_code: this.item_code,
        target_warehouse: this.target_warehouse,
        picking_flow: this.picking_flow,
        is_manual_picking: this.is_manual_picking,
      };
      if (this.material_request) {
        metadata.material_request = this.material_request.docname;
        metadata.target_warehouse = this.material_request.target_warehouse;
        this.target_warehouse = metadata.target_warehouse;
        metadata.item_code = this.material_request.item_code;
      }

      // console.log("update_session_context", JSON.stringify(metadata))
      if (window.AndroidBridge) {
        AndroidBridge.updateMetadata(JSON.stringify(metadata));
      }
      app.updateMetadata(metadata);
      frappe.call({
        method: "iotready_godesi.api.update_activity_session",
        type: "POST",
        args: {
          session_id: this.session_id,
          context: metadata,
        },
        callback: (r) => {
          // console.log("response", JSON.stringify(r));
          if (r.exc) {
            // console.log("reloading!");
            window.location.reload();
          }
        },
        freeze: true,
        freeze_message: "Please wait...",
        async: true,
      }).catch((e) => {
        console.error(e);
        // console.log("reloading!");
        window.location.reload();
      });
    },
    handle_picking_flow_change() {
      if (!this.picking_flow) {
        return
      }
      // console.log("handle_picking_flow_change", this.picking_flow);
      this.update_session_context()
      if (this.picking_flow === 'by_warehouse') {
        // each material request is unique to a combination of item_code and target_warehouse
        // as a result there can be multiple material requests for a single warehouse
        // so we need to get a list of unique warehouses
        this.warehouses = this.open_material_requests.map(mr => ({ target_warehouse: mr.target_warehouse, target_warehouse_name: mr.target_warehouse_name, label: `${mr.target_warehouse_name}(${mr.target_warehouse})` })).filter((v, i, a) => a.findIndex(t => (t.target_warehouse === v.target_warehouse)) === i)
        // console.log("warehouses", this.warehouses);
      } else {
        // each material request is unique to a combination of item_code and target_warehouse
        // as a result there can be multiple material requests for a item_code
        // so we need to get a list of unique items
        this.items = this.open_material_requests.map(mr => ({ item_code: mr.item_code, stock_uom: mr.stock_uom, item_name: mr.item_name, label: `${mr.item_name}(${mr.item_code})` })).filter((v, i, a) => a.findIndex(t => (t.item_code === v.item_code)) === i)
        // console.log("items", this.items);
      }
    },
    handle_target_warehouse_change() {
      if (this.picking_flow === 'by_item_code' || !this.target_warehouse) {
        return
      }
      // console.log("handle_target_warehouse_change", this.target_warehouse)
      this.update_session_context()
      this.material_requests = this.open_material_requests.filter(mr => mr.target_warehouse === this.target_warehouse)
      this.handle_material_requests_change();
    },
    handle_item_code_change() {
      if (this.picking_flow === 'by_warehouse' || !this.item_code) {
        return
      }
      // console.log("handle_item_code_change", this.item_code)
      this.update_session_context()
      this.material_requests = this.open_material_requests.filter(mr => mr.item_code === this.item_code)
    },
    handle_material_requests_change() {
      // console.log("handle_material_requests_change", JSON.stringify(this.material_requests));
      // console.log("selected_material_request", this.selected_material_request);
      // console.log("item_code", this.item_code);
      // console.log("target_warehouse", this.target_warehouse);
      const material_request_docname = this.selected_material_request || this.material_request.docname;
      const new_material_request = this.material_requests.filter(mr => mr.docname === material_request_docname && mr.item_code === this.item_code && mr.target_warehouse === this.target_warehouse)[0];
      if (new_material_request) {
        this.material_request = new_material_request;
      }
      // console.log("material_request", JSON.stringify(this.material_request));
    }
  },
  watch: {
    open_material_requests: {
      handler: function () {
        // console.log("open_material_requests changed", this.open_material_requests, this.item_code, this.target_warehouse, this.material_request)
        this.handle_picking_flow_change();
      },
      deep: true, // Deep watch the array
      immediate: true, // Run this handler immediately after component creation
    },
    items: {
      handler: function () {
        // console.log("items changed", this.items)
        this.handle_item_code_change();
      },
      deep: true, // Deep watch the array
      immediate: true, // Run this handler immediately after component creation
    },
    warehouses: {
      handler: function () {
        // console.log("warehouses changed", this.warehouses)
        this.handle_target_warehouse_change();
      },
      deep: true, // Deep watch the array
      immediate: true, // Run this handler immediately after component creation
    },
    target_warehouses: {
      handler: function () {
        // console.log("target_warehouses changed", this.target_warehouses)
        this.handle_target_warehouse_change();
      },
      deep: true, // Deep watch the array
      immediate: true, // Run this handler immediately after component creation
    },
    material_request: {
      handler: function () {
        if (!this.material_request) {
          return
        }
        // console.log("material_request changed", this.material_request)
        this.update_session_context()
      },
      deep: true, // Deep watch the array
      immediate: true, // Run this handler immediately after component creation
    },
    material_requests: {
      handler: function () {
        // console.log("material_requests changed", this.material_requests)
        this.handle_material_requests_change();
      },
      deep: true, // Deep watch the array
      immediate: true, // Run this handler immediately after component creation
    },
    selected_item_code() {
      this.item_code = this.selected_item_code;
    },
    selected_target_warehouse() {
      this.target_warehouse = this.selected_target_warehouse;
    },
    picking_flow() {
      this.handle_picking_flow_change()
    },
    target_warehouse() {
      this.handle_target_warehouse_change();
    },
    item_code() {
      try {
        const item = this.items.filter(item => item.item_code === this.item_code)[0];
        if (window.AndroidBridge) {
          AndroidBridge.writeToDataLogger("d3edcb21-d7aa-4731-bad8-946651538512", `2,${item.item_name}`);
        }
        if (this.activity === 'Crate Splitting') {
          if (window.AndroidBridge) {
            AndroidBridge.allowEditQuantity(item.stock_uom.toLowerCase() === 'nos');
          }
        }
      } catch (e) {
        console.error(e);
      }
      this.handle_item_code_change();
    },
    is_manual_picking() {
      if (!this.picking_flow == 'by_item_code') {
        return;
      }
      if (window.AndroidBridge) {
        AndroidBridge.allowSubmitButton(this.is_manual_picking);
      }
      const item = this.items.filter(item => item.item_code === this.item_code)[0];
      if (window.AndroidBridge) {
        AndroidBridge.allowEditQuantity(this.is_manual_picking && item && item.stock_uom && item.stock_uom.toLowerCase() === 'nos');
      }
      this.update_session_context()
    }
  },
  mounted() {
    this.item_code = this.selected_item_code;
    this.target_warehouse = this.selected_target_warehouse;
    this.picking_flow = this.selected_picking_flow;
    this.is_manual_picking = this.selected_is_manual_picking;
    // manually trigger these callbacks to fill the option arrays
    this.handle_picking_flow_change();
    this.handle_target_warehouse_change();
    this.handle_item_code_change();
    this.done_mounting = true;
  }
}

</script>

<style>
.form-group {
  padding: 0 !important;
  /* Or whatever value you prefer */
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}

.row-one {
  margin: 0 0 1rem 0;
  margin-bottom: 0rem;
}

.row-one .form-group.col {
  padding-right: 5px;
  padding-left: 5px;
}

.switch {
  position: relative;
  display: inline-block;
  width: 54px;
  height: 28px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  -webkit-transition: .4s;
  transition: .4s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 20px;
  width: 20px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  -webkit-transition: .4s;
  transition: .4s;
}

input:checked+.slider {
  background-color: #2196F3;
}

input:focus+.slider {
  box-shadow: 0 0 1px #2196F3;
}

input:checked+.slider:before {
  -webkit-transform: translateX(26px);
  -ms-transform: translateX(26px);
  transform: translateX(26px);
}

/* Rounded sliders */
.slider.round {
  border-radius: 24px;
}

.slider.round:before {
  border-radius: 50%;
}
</style>
