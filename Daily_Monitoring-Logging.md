Task: "As nobody else at NERDS uc can, you are tasked with monitoring the Kubernetes cluster using command line tools. Please document the most important of your daily monitoring and logging tasks in a small README file."
A screencast of these tasks can be found [on my youtube channel](https://youtu.be/ic4UemyKEgo)

# Daily Monitoring and Logging of Kubernetes Cluster

## Checking cluster health
1. Log onto the Kubernetes master node 'ssh kubernaut@192.168.8.201' and switch to root 'su -'
2. Check the status of all nodes. Ensure all nodes are in the 'Ready' state.
   ```bash
   kubectl get nodes
   ```
3. Ensure core networking (flannel) and DNS are running properly.
   ```bash
   kubectl get pods -n kube-system
   ```
4. Optional: check all pods as well
   ```bash
   kubectl get pods -A
   ```
   
## Checking resource usage
Since we installed a metrics-server, we can check resource usage as well:
1. Check Node Resource Usage
    ```bash
    kubectl top nodes
    ```
2. Check Pod Resource Usage
    ```bash
    kubectl top pods
    ```
3. Check if NodePorts are working
    ```bash
    kubectl get svc -A
    ```

## Logging
1. View cluster events (node reboots, etc)
    ```bash
    kubectl get events --sort-by='.lastTimestamp' -A
    ```
2. Logs of a specific pod (replace <pod-name> and <namespace>)
    ```bash
    kubectl logs <pod-name> -n <namespace>
    ```
3. Example of previous command:
    ```bash
    kubectl logs observation-app-9787f44bf-j7ffv -n default
    ```
   explanation: <pod-name>=observation-app-9787f44bf-j7ffv and <namespace>=default, it can be found via 'kubectl get pods --all-namespaces -l app=observation')
4. Logs from all replicas of our app
    ```bash
    kubectl logs -l app=observation --tail=50 -f
    ```
5. If a pod fails to start, check pod:
    ```bash
    kubectl describe pod <pod-name>
    ```

# Maintenance Tasks
## Adding a new worker node
1. First: follow the steps from our detailed report, we did this with nodes .203, .204 and .205
2. At this point we assume that the prerequisites are met (swap is turned off, etc)
3. On the master node (*201), get the join command:
    ```bash
    kubeadm token create --print-join-command
    ```
4. On the new worker node, run the join command obtained from the master node.
5. Verify on the master node that the new worker node has joined:
6.   ```bash
    kubectl get nodes -w
    ```

## Cluster Startup and Recovery
If you need to run this, you are in big trouble. Read it carefully and try to breath normally. Ideally avoid collapsing.

### Pre-requisites:
1. Ensure that all 5 VMs are running
2. Log into the master node (*201 machine)
3. Keep in mind that you have to wait about 60 seconds sometimes for some operations to propagate. so wait and don't panic.

### Sanity Checks:
3. Disable swap on all nodes (otherwhise kubernetes will not even start)
    ```bash
    sudo swapoff -a
    ```
2. Verify that containerd is running
    ```bash
    systemctl is-active containerd
    ```
3. Check pods
    ```bash
    crictl ps | grep kube-apiserver
    ```
4. Check Network (CNI)
   ```bash
   ip addr show flannel.1
   ```
5. Check rollout status
    ```bash
    kubectl rollout status deployment/observation-app
    ```